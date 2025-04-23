import json
import logging
import asyncio
import pathlib
from agno.agent import RunResponse
from typing import Any, Coroutine, List, Iterable

from agents import build_issue_agent
from models.schemas import StoryList, IssueList
from tools.tool_jira_issue import jira_get_issue_loop
from utils.helpers import load_config, resolve_model

log = logging.getLogger(__name__)

# === Runtime params ===
PROVIDER = "openai"
TEST_SESSION_ID = "test_parallel_issue_agent"
BATCH_SIZE = 50

RUNTIME = load_config("runtime")
MAX_CONCURRENCY = RUNTIME["SESSION"].get("max_concurrency", 10)

MODEL_ID = RUNTIME["MODELS"][PROVIDER]["issue"]
MODEL = resolve_model(provider=PROVIDER, model_id=MODEL_ID)

INPUT_DIR = pathlib.Path(__file__).parent / "../test_data"
INPUT_FILE = INPUT_DIR / "test_story_data.json"
INPUT_STATE_KEY = RUNTIME["SESSION"]["state_stories"]

OUTPUT_DIR = pathlib.Path(__file__).parent / "../test_output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / f"issue_output_parallel_{MODEL_ID}.json"
# ======================


async def run_with_semaphore(
    coro: Coroutine, sem: asyncio.Semaphore, label: str
) -> Any:
    """
    Utility to limit concurrency by running the coroutine under the semaphore.
    Returns either the result or the exception.
    """
    async with sem:
        try:
            log.debug(f"Starting task: {label}")
            result = await coro
            log.debug(f"Finished task: {label}")
            return result
        except Exception as exc:
            log.error("Task %s failed: %s", label, exc, exc_info=False)
            return exc


def _chunks(lst: List[Any], n: int) -> Iterable[List[Any]]:
    """
    Helper to slice lists into chunks.
    Yields successive n-sized chunks from a list.
    """
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


async def run_issue_agent_for_batch(
    stories_batch: StoryList, batch_num: int, session_id: str
) -> RunResponse | Exception:
    """
    Builds and runs an IssueAgent for a single batch of stories.
    Returns the RunResponse or the Exception if it fails.
    """
    batch_label = (
        f"batch {batch_num} ({len(stories_batch)} stories starting {stories_batch[0].get('story_key', 'N/A')})"
        if stories_batch
        else f"batch {batch_num} (empty)"
    )
    log.debug(f"Preparing IssueAgent task for {batch_label}")

    # Create initial state for the batch
    batch_state = {INPUT_STATE_KEY: {"stories": stories_batch}}

    # Build agent instance for this specific batch
    agent = build_issue_agent(
        model=MODEL,
        tools=[jira_get_issue_loop],
        initial_state=batch_state,
        debug=False,
    )
    agent.show_tool_calls = True

    # Run agent (run_with_semaphore will catch exceptions from this await)
    response = await agent.arun(
        f"Fetch issue details for {len(stories_batch)} stories ({batch_label})",
        session_id=session_id,
    )
    return response


async def run_issue_agent_parallel():
    log.info("--- Starting Parallel Agno IssueAgent Test ---")

    stories_list: StoryList = []
    try:
        with open(INPUT_FILE, "r") as f:
            raw_input_data = json.load(f)
            if isinstance(raw_input_data, dict) and "stories" in raw_input_data:
                stories_list = raw_input_data["stories"]

            # Allow loading a direct list
            elif isinstance(raw_input_data, list):
                stories_list = raw_input_data
            else:
                raise ValueError(
                    "Input file format not recognized (expected list or {'stories': list})"
                )

            log.info(f"Loaded {len(stories_list)} stories from {INPUT_FILE}.")
            if not stories_list:
                log.warning("Input story list is empty.")
                return

    except Exception as e:
        log.critical(
            f"Failed to load or parse input file {INPUT_FILE}: {e}", exc_info=True
        )
        raise

    # Prepare and run the concurrent tasks
    tasks = []
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    log.info(f"Creating issue fetch tasks in batches of {BATCH_SIZE}...")

    for i, story_batch in enumerate(_chunks(stories_list, BATCH_SIZE)):
        if not story_batch:
            continue  # Skip empty chunks
        batch_num = i + 1

        task_session_id = f"{TEST_SESSION_ID}_batch_{batch_num}"
        task_label = f"issue_agent_batch_{batch_num}"

        tasks.append(
            run_with_semaphore(
                run_issue_agent_for_batch(story_batch, batch_num, task_session_id),
                sem,
                task_label,
            )
        )

    log.info(
        f"Running {len(tasks)} batch tasks concurrently (max concurrency: {MAX_CONCURRENCY})..."
    )
    batch_results = await asyncio.gather(*tasks)
    log.info("All parallel batch tasks completed.")

    # Aggregate results
    aggregated_issues: IssueList = []
    failed_batches = 0
    processed_stories_count = 0  # Count stories in successful batches

    log.info("Aggregating results from batches...")
    for i, result in enumerate(batch_results):
        batch_num = i + 1

        # Determine number of stories in the original batch for logging
        start_index = i * BATCH_SIZE
        original_batch_size = len(stories_list[start_index : start_index + BATCH_SIZE])

        # Success
        if isinstance(result, RunResponse) and isinstance(result.content, IssueList):
            num_issues_found = len(result.content.issues)
            log.debug(
                f"Batch {batch_num} succeeded, found {num_issues_found} / {original_batch_size} issues."
            )
            aggregated_issues.extend(result.content.issues)

            # Consider batch processed even if not all issues found
            processed_stories_count += original_batch_size

        # Task failed (exception caught by run_with_semaphore)
        elif isinstance(result, Exception):
            log.warning(
                f"Batch {batch_num} ({original_batch_size} stories) failed with exception: {result}"
            )
            failed_batches += 1
        else:
            # Unexpected result type
            content_type = (
                type(getattr(result, "content", None)).__name__
                if isinstance(result, RunResponse)
                else type(result).__name__
            )
            log.error(
                f"Batch {batch_num} ({original_batch_size} stories) returned unexpected result type: {content_type}"
            )
            failed_batches += 1

    log.info(
        f"Aggregation complete. Processed {len(batch_results)} batches. "
        f"Failed batches: {failed_batches}. Total issues successfully fetched: {len(aggregated_issues)}."
    )

    # Final output processing
    final_issue_list_obj = IssueList(issues=aggregated_issues)

    # Save + verify output
    log.info(f"Saving aggregated IssueAgent output to: {OUTPUT_FILE}")
    try:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(final_issue_list_obj.model_dump(), f, indent=4)
            log.info(f"Saved aggregated structured output to {OUTPUT_FILE}")
    except IOError as e:
        log.error(f"Failed to write output file {OUTPUT_FILE}: {e}")
    except Exception as e:
        log.error(f"Failed during final output saving: {e}")

    # Basic assertion: check if we got result from batches processed
    if stories_list:
        assert len(aggregated_issues) > 0 or failed_batches == len(batch_results), (
            f"Expected some issues or all batches to fail. Got {len(aggregated_issues)} issues, {failed_batches}/{len(batch_results)} failed batches."
        )
        log.info(
            f"Verification passed (Processed {len(batch_results) - failed_batches}/{len(batch_results)} batches successfully)."
        )
    else:
        assert len(aggregated_issues) == 0, (
            "Should have no issues if no stories were input."
        )
        log.info("Verification passed (no stories input, no issues found).")

    log.info("--- Finished Parallel Agno IssueAgent Test ---")


if __name__ == "__main__":
    from utils.logging_setup import setup_logging

    setup_logging(level=logging.INFO)
    log.info("Starting IssueAgent parallel test execution...")

    try:
        asyncio.run(run_issue_agent_parallel())
        log.info("IssueAgent parallel test completed successfully.")
    except Exception as e:
        log.exception(f"IssueAgent parallel test failed: {e}")
