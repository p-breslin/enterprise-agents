import sys
import json
import logging
import asyncio
import pathlib
from agno.agent import RunResponse

from callbacks import log_agno_callbacks
from agents.GraphAgent import build_graph_agent
from tools.tool_arango_upsert import arango_upsert
from utils_agno import load_config, resolve_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)


# === Runtime params ===
runtime_params = load_config("runtime")

model_provider = "openai"
model_id = runtime_params["MODELS"][model_provider]["graph"]
MODEL = resolve_model(provider=model_provider, model_id=model_id)

input_dir = pathlib.Path(__file__).parent / "test_data"
output_dir = pathlib.Path(__file__).parent / "test_output"
output_dir.mkdir(exist_ok=True)
# ======================


async def run_graph_agent_test(test_type: str):
    """
    Runs the GrapAgent test for 'epic', 'story', or 'issue'.
    """
    if test_type not in ["epic", "story", "issue"]:
        logger.critical(f"Invalid test_type '{test_type}'.")
        return
    logger.info(f"--- Starting Isolated Agno GraphAgent Test ({test_type.upper()}) ---")

    # --- Determine Test Config ---
    if test_type == "epic":
        input_file_name = "test_epic_data.json"
        prompt = "epic_graph_prompt"
        INPUT_STATE_KEY = "epics_data_input"

    elif test_type == "story":
        input_file_name = "test_story_data.json"
        prompt = "story_graph_prompt"
        INPUT_STATE_KEY = "stories_data_input"

    elif test_type == "issue":
        input_file_name = "test_issue_data.json"
        prompt = "issue_graph_prompt"
        INPUT_STATE_KEY = "issues_data_input"

    TEST_SESSION_ID = f"test_session_graph_agent_{test_type}"
    INPUT_FILE = input_dir / input_file_name

    # --- Load Input Data ---
    input_state_data = {}
    try:
        with open(INPUT_FILE, "r") as f:
            raw_input_data = json.load(f)
            input_state_data[INPUT_STATE_KEY] = raw_input_data
            logger.info(
                f"Loaded input data from {INPUT_FILE} into state key '{INPUT_STATE_KEY}'."
            )
    except Exception as e:
        logger.critical(f"Failed to load input file {INPUT_FILE}: {e}")
        raise

    # --- Agent Setup ---
    agent = build_graph_agent(
        model=MODEL,
        tools=[arango_upsert],
        initial_state=input_state_data,
        prompt=prompt,
    )
    agent.debug_mode = True
    agent.show_tool_calls = True
    logger.info(f"Built Agno GraphAgent using model {model_id}")

    # --- Run Agent ---
    trigger_message = f"Update graph for {test_type} data in state"
    final_response: RunResponse = None

    logger.info("Running GraphAgent...")
    try:
        # Use agent.arun for async execution, or agent.run for sync
        # Provide input state here
        response = await agent.arun(trigger_message, session_id=TEST_SESSION_ID)
        final_response = response
        run_label = f"GraphUpdateAgent_{test_type}_Test"
        log_agno_callbacks(final_response, run_label, filename=f"{run_label}_callbacks")

    except Exception as e:
        logger.exception(f"GraphUpdateAgent ({test_type}) execution failed.")
        raise

    if final_response:
        # Check if agent produced *some* response without throwing an exception
        assert final_response is not None, (
            f"GraphUpdateAgent ({test_type}) failed to produce a response."
        )
    else:
        logger.error(
            f"GraphUpdateAgent ({test_type}) did not produce a final response object."
        )
        assert False, f"GraphUpdateAgent ({test_type}) test failed: No final response."

    logger.info(
        f"--- Finished Isolated Agno GraphUpdateAgent Test ({test_type.upper()}) ---"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ["epic", "story", "issue"]:
        print("Usage: python test_GraphUpdateAgent.py <epic|story|issue>")
        sys.exit(1)

    test_type_arg = sys.argv[1]

    try:
        asyncio.run(run_graph_agent_test(test_type_arg))
        logger.info(f"GraphUpdateAgent test ({test_type_arg}) completed.")
    except Exception:
        logger.exception(f"GraphUpdateAgent test ({test_type_arg}) failed.")
        sys.exit(1)  # Exit with error code on failure
