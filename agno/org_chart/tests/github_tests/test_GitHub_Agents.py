import pathlib
import logging
import asyncio
import argparse
import datetime
from datetime import timedelta
from dotenv import load_dotenv

from utils.helpers import (
    load_config,
    resolve_model,
    resolve_output_schema,
    parse_json,
    validate_output,
    inject_state,
)

from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
from agno.utils.pprint import pprint_run_response

from agents.agent_factory import build_agent
from utils.logging_setup import setup_logging
from integrations.github_mcp import get_github_mcp_config

load_dotenv()
setup_logging()
log = logging.getLogger(__name__)


async def run_test(test_name: str):
    """Runs a specific agent test based on the configuration name."""
    log.info(f"=== Starting Test: {test_name} ===")

    # General runtime settings
    runtime = load_config("runtime")

    # Global configuration
    configs = load_config("test_configs")
    provider = configs["provider"]
    debug = configs["debug"]

    # Agent configuration
    cfg = configs[test_name]
    model_key = cfg["model_key"]
    model_id = runtime["MODELS"][provider][model_key]
    model = resolve_model(provider, model_id)

    # Session configuration
    session_id = cfg.get("session_id", f"test_session_{test_name}")
    agent_type = cfg.get("agent_type")
    if not agent_type:
        log.error(f"Missing 'agent_type' in config for test '{test_name}'")
        return

    trigger = cfg.get("trigger_message", "Run agent task based on input.")
    output_schema_name = cfg.get("output_schema")
    output_schema_model = resolve_output_schema(output_schema_name)

    # Define output
    output_dir = pathlib.Path(__file__).parent / configs["output_dir"]
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"test_{test_name}_output_{model_id}.json"

    # Define Input
    input_dir = pathlib.Path(__file__).parent / configs["input_dir"]
    input_file = input_dir / cfg["input_file"]
    input_state_key = cfg["input_state_key"]

    # Resolve the initial state
    initial_state = inject_state(input_file, input_state_key)

    # Cutoff date
    cutoff = cfg.get("cutoff")
    if cutoff:
        cutoff_date = (datetime.date.today() - timedelta(days=cutoff)).strftime(
            "%Y-%m-%d"
        )
        log.info(f"Cutoff-date passed: {cutoff_date}")
        initial_state["cutoff_date"] = cutoff_date

    # Tool setup
    mcp_cmd, mcp_env = get_github_mcp_config()

    # Execution
    try:
        async with MCPTools(mcp_cmd, env=mcp_env) as mcp_tools:
            agent = build_agent(
                agent_type=agent_type,
                model=model,
                tools=[mcp_tools],
                initial_state=initial_state,
                debug=debug,
            )

            # Run agent
            log.info(f"Running {agent.name} with trigger: '{trigger}'...")
            resp: RunResponse = await agent.arun(trigger, session_id=session_id)
            assert resp.content, f"{agent.name} returned empty content"
            pprint_run_response(resp, markdown=False)

            # Validate and save output
            log.info(f"Parsing and validating output for {test_name}...")
            json_obj = parse_json(resp.content)
            validate_output(output_file, json_obj, output_schema_model)

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
