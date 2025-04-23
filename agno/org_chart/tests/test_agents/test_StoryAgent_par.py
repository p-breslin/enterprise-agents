import json
import logging
import asyncio
import pathlib
from typing import Any, Coroutine

from agno.agent import RunResponse
from utils.logging_setup import setup_logging
from models.schemas import Epic, EpicList, StoryList
from utils.helpers import load_config, resolve_model

from agents import build_story_agent
from tools.tool_jira_epic_issues import jira_get_epic_issues

log = logging.getLogger(__name__)

# === Runtime params ===
PROVIDER = "openai"
TEST_SESSION_ID = "test_parallel_story_agent"

RUNTIME = load_config("runtime")
MAX_CONCURRENCY = RUNTIME["SESSION"].get("max_concurrency", 10)

MODEL_ID = RUNTIME["MODELS"][PROVIDER]["story"]
MODEL = resolve_model(provider=PROVIDER, model_id=MODEL_ID)

INPUT_DIR = pathlib.Path(__file__).parent / "../test_data"
INPUT_FILE = INPUT_DIR / "test_epic_data.json"
INPUT_STATE_KEY = RUNTIME["SESSION"]["state_epics"]

OUTPUT_DIR = pathlib.Path(__file__).parent / "../test_output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / f"story_output_parallel_{MODEL_ID}.json"
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


async def run_story_agent(epic_dict: Epic, session_id: str) -> RunResponse | Exception:
    """
    Builds and runs a StoryAgent for a single epic.
    Returns the RunResponse or the Exception if it fails.
    """
    epic_key = epic_dict.get("epic_key", "[UNKNOWN]")
    log.debug(f"Preparing StoryAgent task for epic: {epic_key}")

    # Create initial state containing only the single epic's data
    single_epic_state = {INPUT_STATE_KEY: epic_dict}

    # Build agent instance for this specific task
    agent = build_story_agent(
        model=MODEL,
        tools=[jira_get_epic_issues],
        initial_state=single_epic_state,
        debug=False,
    )
    agent.show_tool_calls = True

    # Run the agent (run_with_semaphore will catch exceptions from this await)
    response = await agent.arun(
        f"Get stories for epic {epic_key}", session_id=session_id
    )
    return response


async def run_story_agent_parallel():
    log.info("--- Starting Parallel Agno StoryAgent Test ---")

    # Load input Epics data
    epics_list: EpicList = []
    try:
        with open(INPUT_FILE, "r") as f:
            raw_input_data = json.load(f)
            if isinstance(raw_input_data, dict) and "epics" in raw_input_data:
                epics_list = raw_input_data["epics"]

            # Allow loading a direct list too
            elif isinstance(raw_input_data, list):
                epics_list = raw_input_data
            else:
                raise ValueError(
                    "Input file format not recognized (expected list or {'epics': list})"
                )

            log.info(f"Loaded {len(epics_list)} epics from {INPUT_FILE}.")
            if not epics_list:
                log.warning("Fatal: input epic list is empty.")
                return

    except Exception as e:
        log.critical(
            f"Failed to load or parse input file {INPUT_FILE}: {e}", exc_info=True
        )
        raise

    # Prepare and run the concurrent tasks
    tasks = []
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    log.info(f"Creating {len(epics_list)} parallel StoryAgent tasks...")

    for i, epic_data in enumerate(epics_list):
        epic_key = epic_data.get("epic_key", f"unknown_epic_{i}")
        task_session_id = f"{TEST_SESSION_ID}_{epic_key}"
        task_label = f"story_agent_epic_{epic_key}"

        tasks.append(
            run_with_semaphore(
                run_story_agent(epic_data, task_session_id),
                sem,
                task_label,
            )
        )

    log.info(
        f"Running {len(tasks)} tasks concurrently (max concurrency: {MAX_CONCURRENCY})..."
    )
    results = await asyncio.gather(*tasks)
    log.info("All parallel tasks completed.")

    # Aggregate results
    aggregated_stories: StoryList = []
    failed_epics = 0
    processed_epics = 0

    log.info("Aggregating results...")
    for i, result in enumerate(results):
        epic_key = epics_list[i].get("epic_key", f"unknown_epic_{i}")

        # Success
        if isinstance(result, RunResponse) and isinstance(result.content, StoryList):
            N_stories = len(result.content.stories)
            log.debug(f"Task for epic {epic_key} succeeded, found {N_stories} stories.")
            aggregated_stories.extend(result.content.stories)
            processed_epics += 1

        # Task failed (exception caught by run_with_semaphore)
        elif isinstance(result, Exception):
            log.warning(f"Task for epic {epic_key} failed with exception: {result}")
            failed_epics += 1
        else:
            # Unexpected result type (e.g., agent returned wrong content type)
            content_type = (
                type(getattr(result, "content", None)).__name__
                if isinstance(result, RunResponse)
                else type(result).__name__
            )
            log.error(
                f"Task for epic {epic_key} returned unexpected result type: {content_type}"
            )
            failed_epics += 1

    log.info(
        f"Successfully processed {processed_epics} epics, "
        f"failed for {failed_epics} epics. Total stories found: {len(aggregated_stories)}."
    )

    # Final output processing
    final_story_list_obj = StoryList(stories=aggregated_stories)

    # Save + verify output
    log.info(f"Saving aggregated StoryAgent output to: {OUTPUT_FILE}")
    try:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(final_story_list_obj.model_dump(), f, indent=4)
            log.info(f"Saved aggregated structured output to {OUTPUT_FILE}")
    except IOError as e:
        log.error(f"Failed to write output file {OUTPUT_FILE}: {e}")
    except Exception as e:
        log.error(f"Failed during final output saving: {e}")

    # Basic assertion: check if we processed any stories if epics were input
    if epics_list:
        assert processed_epics > 0 or failed_epics == len(epics_list), (
            "Expected at least one epic to be processed successfully if input was provided, unless all failed."
        )
        log.info(
            f"Verification check passed (processed {processed_epics}/{len(epics_list)} epics)."
        )
    else:
        assert len(aggregated_stories) == 0, (
            "Should have no stories if no epics were input."
        )
        log.info("Verification passed (no epics input, no stories found).")

    log.info("--- Finished Parallel Agno StoryAgent Test ---")


if __name__ == "__main__":
    from utils.logging_setup import setup_logging

    setup_logging(level=logging.INFO)
    log.info("Starting StoryAgent parallel test execution...")

    try:
        asyncio.run(run_story_agent_parallel())
        log.info("StoryAgent parallel test completed successfully.")
    except Exception as e:
        log.exception(f"StoryAgent parallel test failed: {e}")
