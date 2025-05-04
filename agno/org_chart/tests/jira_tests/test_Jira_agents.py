import pathlib
import logging
import asyncio
import argparse
from dotenv import load_dotenv
from typing import Dict, Any, List

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
from tools import jira_search, jira_get_epic_issues, jira_get_issue_loop, arango_upsert


load_dotenv()
setup_logging()
log = logging.getLogger(__name__)

# Tool mapping
JIRA_TOOL_SETS: Dict[str, List[Any]] = {
    "jira_search": [jira_search],
    "jira_epic_issues": [jira_get_epic_issues],
    "jira_get_issue": [jira_get_issue_loop],
    "arango_upsert": [arango_upsert],
}


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
    model_key = cfg["model_key"]
    model_id = runtime["MODELS"][provider][model_key]

    # Session configuration
    session_id = cfg.get("session_id", f"test_session_{test_name}")
    trigger = cfg.get("trigger_message", "Run agent task based on input.")
    output_schema = cfg["schema"]
    if output_schema:
        output_schema_model = resolve_output_schema(output_schema)

    # Define output
    output_dir = pathlib.Path(__file__).parent / global_cfg["output_dir"]
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"test_{test_name}_output_{model_id}.json"

    # Define Input
    if cfg["input_file"]:
        input_dir = pathlib.Path(__file__).parent / global_cfg["input_dir"]
        input_file = input_dir / cfg["input_file"]
        input_state_key = cfg["input_state_key"]
        initial_state = inject_state(input_file, input_state_key)
    else:
        initial_state = None

    # Execution
    try:
        agent = build_agent(
            agent_type=cfg["agent_type"],
            model=resolve_model(provider, model_id),
            tools=JIRA_TOOL_SETS[cfg["tools"]],
            initial_state=initial_state,
            prompt_key=cfg["prompt_key"],
            response_model=cfg["response_model"],
            debug=global_cfg["debug"],
        )

        # Run agent
        log.info(f"Running {agent.name} with trigger: '{trigger}'...")
        resp: RunResponse = await agent.arun(trigger, session_id=session_id)
        assert resp.content, f"{agent.name} returned empty content"
        pprint_run_response(resp, markdown=False)

        # Validate and save output
        log.info(f"Parsing and validating output for {test_name}...")
        if output_schema:
            validate_output(output_file, resp.content, output_schema_model)

        log.info(f"=== Finished Test: {test_name}. Output saved to {output_file} ===")

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
