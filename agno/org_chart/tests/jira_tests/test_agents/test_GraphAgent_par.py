import sys
import json
import logging
import asyncio
import pathlib
from agno.agent import RunResponse
from typing import Any, Coroutine, List, Dict

from agents import build_graph_agent
from tools.tool_arango_upsert import arango_upsert
from utils.helpers import load_config, resolve_model

log = logging.getLogger(__name__)

# === Runtime params ===
PROVIDER = "openai"
TEST_SESSION_ID = "test_parallel_graph_agent"

RUNTIME = load_config("runtime")
MAX_CONCURRENCY = RUNTIME["SESSION"].get("max_concurrency", 10)

MODEL_ID = RUNTIME["MODELS"][PROVIDER]["graph"]
MODEL = resolve_model(provider=PROVIDER, model_id=MODEL_ID)

INPUT_DIR = pathlib.Path(__file__).parent / "../test_data"
OUTPUT_DIR = pathlib.Path(__file__).parent / "../test_output"
OUTPUT_DIR.mkdir(exist_ok=True)
# ======================

# Mapping test type to necessary configurations
TEST_CONFIG = {
    "epic": {
        "input_file": "test_epic_data.json",
        "prompt_key": RUNTIME["PROMPTS"]["graph_epic"],
        "state_key": RUNTIME["SESSION"]["state_epics"],  # Key for prompt
        "data_list_key": "epics",  # Key in JSON file containing the list
        "item_id_key": "epic_key",  # Key within item dict for logging
    },
    "story": {
        "input_file": "test_story_data.json",
        "prompt_key": RUNTIME["PROMPTS"]["graph_story"],
        "state_key": RUNTIME["SESSION"]["state_stories"],
        "data_list_key": "stories",
        "item_id_key": "story_key",
    },
    "issue": {
        "input_file": "test_issue_data.json",
        "prompt_key": RUNTIME["PROMPTS"]["graph_issue"],
        "state_key": RUNTIME["SESSION"]["state_issues"],
        "data_list_key": "issues",
        "item_id_key": "story_key",
    },
}
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


async def run_single_graph_update(
    item_dict: Dict[str, Any],  # Takes one epic/story/issue dict
    item_type: str,  # 'epic', 'story', or 'issue'
    session_id: str,
) -> RunResponse | Exception:
    """
    Builds and runs a GraphAgent for a single item (epic, story, or issue).
    Returns the RunResponse or the Exception if it fails.
    """
    cfg = TEST_CONFIG[item_type]
    prompt_key = cfg["prompt_key"]
    state_key = cfg["state_key"]
    item_id_key = cfg["item_id_key"]
    item_id = item_dict.get(item_id_key, "[UNKNOWN_ID]")

    log.debug(f"Preparing GraphAgent task for {item_type}: {item_id}")

    # Create initial state containing only the single item's data
    single_item_state = {state_key: item_dict}

    # Build agent instance for this specific task
    agent = build_graph_agent(
        model=MODEL,
        tools=[arango_upsert],
        initial_state=single_item_state,
        prompt=prompt_key,
        debug=False,
    )
    agent.show_tool_calls = True

    # Run agent (run_with_semaphore will catch exceptions from this await)
    response = await agent.arun(
        f"Update graph for {item_type} {item_id}", session_id=session_id
    )
    return response


async def run_graph_agent_parallel(test_type: str):
    """
    Runs GraphAgent test in parallel for each item ('epic', 'story', or 'issue').
    """
    if test_type not in TEST_CONFIG:
        log.critical(
            f"Invalid test_type '{test_type}'. Must be one of {list(TEST_CONFIG.keys())}"
        )
        return
    log.info(f"--- Starting Parallel Agno GraphAgent Test ({test_type.upper()}) ---")

    cfg = TEST_CONFIG[test_type]
    input_file_name = cfg["input_file"]
    data_list_key = cfg["data_list_key"]
    item_id_key = cfg["item_id_key"]
    INPUT_FILE = INPUT_DIR / input_file_name

    item_list: List[Dict[str, Any]] = []
    try:
        with open(INPUT_FILE, "r") as f:
            raw_input_data = json.load(f)

            # Expecting the data under a specific key (e.g., "epics", "stories")
            if isinstance(raw_input_data, dict) and data_list_key in raw_input_data:
                item_list = raw_input_data[data_list_key]
                if not isinstance(item_list, list):
                    raise ValueError(f"Data under key '{data_list_key}' is not a list.")
            else:
                raise ValueError(
                    f"Input file format not recognized or key '{data_list_key}' missing."
                )

            log.info(f"Loaded {len(item_list)} {test_type} items from {INPUT_FILE}.")
            if not item_list:
                log.warning(f"Input {test_type} list is empty.")
                return

    except FileNotFoundError:
        log.critical(f"Input file not found: {INPUT_FILE}", exc_info=True)
        raise
    except Exception as e:
        log.critical(
            f"Failed to load or parse input file {INPUT_FILE}: {e}", exc_info=True
        )
        raise

    # Prepare and Rrn concurrent tasks
    tasks = []
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    log.info(
        f"Creating {len(item_list)} parallel GraphAgent tasks for {test_type} items..."
    )

    for i, item_data in enumerate(item_list):
        item_id = item_data.get(item_id_key, f"unknown_{test_type}_{i}")
        task_session_id = f"{TEST_SESSION_ID}_{test_type}_{item_id}"
        task_label = f"graph_agent_{test_type}_{item_id}"

        tasks.append(
            run_with_semaphore(
                run_single_graph_update(item_data, test_type, task_session_id),
                sem,
                task_label,
            )
        )

    log.info(
        f"Running {len(tasks)} tasks concurrently (max concurrency: {MAX_CONCURRENCY})..."
    )
    results = await asyncio.gather(*tasks)
    log.info("All parallel graph update tasks completed.")

    # Aggregate results (count Success/Failure)
    success_count = 0
    failure_count = 0

    log.info("Aggregating results...")
    for i, result in enumerate(results):
        item_id = item_list[i].get(item_id_key, f"unknown_{test_type}_{i}")

        # Basic success check: Agent ran and returned a response object
        if isinstance(result, RunResponse):
            log.debug(f"Task for {test_type} {item_id} succeeded.")
            success_count += 1

        # Task failed (exception caught by run_with_semaphore)
        elif isinstance(result, Exception):
            log.warning(f"Task for {test_type} {item_id} failed: {result}")
            failure_count += 1
        else:
            # Unexpected result type
            log.error(
                f"Task for {test_type} {item_id} returned unexpected result type: {type(result)}"
            )
            failure_count += 1

    log.info(
        f"Aggregation complete. Successfully processed {success_count} / {len(item_list)} {test_type} items. "
        f"Failures: {failure_count}."
    )

    # Verification - assert that all tasks completed without unexpected errors
    assert failure_count == 0, f"{failure_count} graph agent tasks failed. Check logs."
    assert success_count == len(item_list), (
        "Number of successful tasks doesn't match input items."
    )
    log.info(
        f"Verification passed ({success_count}/{len(item_list)} tasks successful)."
    )
    log.info(f"--- Finished Parallel Agno GraphAgent Test ({test_type.upper()}) ---")


if __name__ == "__main__":
    from utils.logging_setup import setup_logging

    # CLI args
    if len(sys.argv) != 2 or sys.argv[1] not in TEST_CONFIG:
        print(f"Usage: python {sys.argv[0]} <{'|'.join(TEST_CONFIG.keys())}>")
        sys.exit(1)
    test_type_arg = sys.argv[1]

    # Save logs to file
    setup_logging()
    root_log = logging.getLogger()

    filename = OUTPUT_DIR / f"test_graph_agent_parallel_{test_type_arg}.log"
    file_handler = logging.FileHandler(filename, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    root_log.addHandler(file_handler)
    log = logging.getLogger(__name__)

    log.info(
        f"Starting GraphAgent parallel test execution for type: {test_type_arg}..."
    )
    try:
        asyncio.run(run_graph_agent_parallel(test_type_arg))
        log.info(f"GraphAgent parallel test ({test_type_arg}) completed successfully.")
    except Exception as e:
        log.exception(f"GraphAgent parallel test ({test_type_arg}) failed: {e}")
        sys.exit(1)
