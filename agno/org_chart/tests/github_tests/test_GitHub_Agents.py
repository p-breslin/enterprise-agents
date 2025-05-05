import pathlib
import logging
import asyncio
import argparse
import datetime
from datetime import timedelta
from dotenv import load_dotenv
from typing import List, Any, Dict

from utils.helpers import (
    load_config,
    resolve_model,
    resolve_output_schema,
    validate_output,
    inject_state,
)

from agno.agent import RunResponse
from agno.utils.pprint import pprint_run_response

from agents.agent_factory import build_agent
from utils.logging_setup import setup_logging

from tools import arango_upsert
from tools.tools_github import (
    list_commits,
    get_pull_request,
    get_pull_request_status,
    get_pull_request_reviews,
    get_pull_request_files,
    search_issues,
    search_repositories,
)

load_dotenv()
setup_logging()
log = logging.getLogger(__name__)


AGENT_TOOL_MAP: Dict[str, List[Any]] = {
    "RepoAgent": [search_repositories],
    "PRNAgent": [search_issues],
    "PRDAgent": [
        get_pull_request,
        get_pull_request_status,
        get_pull_request_reviews,
        get_pull_request_files,
    ],
    "PRCAgent": [list_commits],
    "GraphAgent": [arango_upsert],
}
# -------------------------------------------------------------------


async def run_test(test_name: str):
    """Runs a specific agent test based on the configuration name."""
    log.info(f"=== Starting Test: {test_name} ===")

    # General runtime settings
    runtime = load_config("runtime")

    # Global configuration
    global_cfg = load_config("test_configs")
    provider = global_cfg["provider"]

    # Agent configuration
    cfg = global_cfg[test_name]
    agent_type = cfg["agent_type"]
    model_key = cfg["model_key"]
    model_id = runtime["MODELS"][provider][model_key]

    # Session configuration
    session_id = cfg.get("session_id", f"test_session_{test_name}")
    trigger = cfg.get("trigger_message", "Run agent task based on input.")
    output_schema = cfg["schema"]
    if output_schema:
        output_schema_model = resolve_output_schema(output_schema)

    # Define output
    output_dir = pathlib.Path(__file__).parent.parent / global_cfg["output_dir"]
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"test_{agent_type}_output_{model_id}.json"

    # Define Input (different for the first agent i.e. the RepoAgent)
    input_state_key = cfg["input_state_key"]
    if agent_type == "RepoAgent":
        initial_state = {}
        initial_state[input_state_key] = runtime["GITHUB"]["org"]
    else:
        # Resolve the initial state
        input_dir = pathlib.Path(__file__).parent / global_cfg["input_dir"]
        input_file = input_dir / cfg["input_file"]
        initial_state = inject_state(input_file, input_state_key)

    # Cutoff date
    cutoff = cfg["cutoff"]
    if cutoff:
        cutoff_date = (datetime.date.today() - timedelta(days=cutoff)).strftime(
            "%Y-%m-%d"
        )
        log.info(f"Cutoff-date passed: {cutoff_date}")
        initial_state["cutoff_date"] = cutoff_date

    # Select the correct set of direct tools
    tools = AGENT_TOOL_MAP.get(agent_type)
    log.info(f"Using tools: {[getattr(t, '__name__', repr(t)) for t in tools]}")

    try:
        agent = build_agent(
            agent_type=agent_type,
            model=resolve_model(provider, model_id),
            tools=tools,
            initial_state=initial_state,
            prompt_key=cfg["prompt_key"],
            debug=global_cfg["debug"],
        )

        # Run agent
        log.info(f"Running {agent.name} with trigger: '{trigger}'...")
        resp: RunResponse = await agent.arun(trigger, session_id=session_id)
        assert resp.content, f"{agent.name} returned empty content"
        pprint_run_response(resp, markdown=False)

        # Validate and save output
        log.info(f"Parsing and validating output for {agent_type}...")
        if output_schema:
            validate_output(output_file, resp.content, output_schema_model)

        log.info(f"=== Finished Test: {test_name}. ===")

    except FileNotFoundError as e:
        log.error(f"Missing file during test '{test_name}': {e}")
    except ValueError as e:
        log.error(f"Data validation or parsing error during test '{test_name}': {e}")
    except AssertionError as e:
        log.error(f"Assertion failed during test '{test_name}': {e}")
    except Exception as e:
        log.error(
            f"An unexpected error occurred during test '{test_name}': {e}",
            exc_info=True,
        )


# CLI argument parsing
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run specific Agent test.")
    parser.add_argument(
        "test_name",
        metavar="TEST_NAME",
        type=str,
    )
    args = parser.parse_args()
    asyncio.run(run_test(args.test_name))
