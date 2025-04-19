import sys
import json
import asyncio
import logging
import pathlib
from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from debug_callbacks import trace_event
from google_adk.agents.GraphUpdateAgent import build_graph_agent
from google_adk.utils_adk import load_tools, load_config, resolve_model

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# === Runtime params ===

RUNTIME_PARAMS = load_config("runtime")
APP_NAME = RUNTIME_PARAMS["SESSION"]["app_name"]
USER_ID = RUNTIME_PARAMS["SESSION"]["user_id"]

OUTPUTS = RUNTIME_PARAMS["OUTPUTS"]
AGENT_OUTPUT_KEY = OUTPUTS["graph"]

model_provider = "google"
SELECTED_MODEL = RUNTIME_PARAMS["MODELS"][model_provider]["graph"]
MODEL = resolve_model(SELECTED_MODEL, provider=model_provider)

# Define Input (story data from IssueAgent)
INPUT_DIR = pathlib.Path(__file__).parent / "test_data"

# ======================


async def run_graph_agent_test(test_type: str):
    if test_type not in ["epic", "story", "issue"]:
        logger.critical(
            f"Invalid test_type '{test_type}'. Must be 'epic', 'story', or 'issue'."
        )
        return
    logger.info("--- Starting Isolated GraphUpdateAgent Test ---")

    # Determine configuration based on test_type
    if test_type == "epic":
        input_file_name = "test_epic_data.json"
        prompt_name = "epic_graph_prompt"
        input_state_key = "epic_graph_input"
        test_session_id = f"test_session_graph_agent_{test_type}"
        graph_output_key = f"{AGENT_OUTPUT_KEY}_epics_test"
    elif test_type == "story":
        input_file_name = "test_story_data.json"
        prompt_name = "story_graph_prompt"
        input_state_key = "story_graph_input"
        test_session_id = f"test_session_graph_agent_{test_type}"
        graph_output_key = f"{AGENT_OUTPUT_KEY}_stories_test"
    else:
        input_file_name = "test_issue_data.json"
        prompt_name = "issue_graph_prompt"
        input_state_key = "issue_graph_input"
        test_session_id = f"test_session_graph_agent_{test_type}"
        graph_output_key = f"{AGENT_OUTPUT_KEY}_issues_test"

    input_file = INPUT_DIR / input_file_name

    _, _, _, arango_custom = await load_tools()
    logger.info("Tools loaded.")

    session_service = InMemorySessionService()
    try:
        session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=test_session_id
        )
        logger.info(f"Deleted existing session: {test_session_id}")
    except KeyError:
        logger.info(f"Session {test_session_id} not found, creating new.")
    session = session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=test_session_id
    )
    logger.info(f"Created session: {test_session_id}")

    # Load input data and put it into state
    try:
        with open(input_file, "r") as f:
            data = json.load(f)
        session.state[input_state_key] = json.dumps(data)
    except Exception as e:
        logger.critical(f"Failed to load or process input file {input_file}: {e}")
        raise

    # --- Agent Setup ---
    agent = build_graph_agent(
        model=MODEL,
        prompt=prompt_name,
        tools=[arango_custom],
        input_key=input_state_key,  # Tell agent where to read data
        output_key=graph_output_key,  # Agent saves its result here
    )
    logger.info(f"Built GraphUpdateAgent ({test_type}) and prompt {prompt_name}")

    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    # --- Run Agent ---
    trigger_message = types.Content(
        role="user",
        parts=[types.Part(text=f"Update graph for {test_type} data in state")],
    )
    output = None

    logger.info(f"Running GraphUpdateAgent ({test_type})...")
    async for event in runner.run_async(
        user_id=USER_ID, session_id=test_session_id, new_message=trigger_message
    ):
        trace_event(event)
        if event.is_final_response() and event.content and event.content.parts:
            output = event.content.parts[0].text
            logger.info(f"GraphUpdateAgent ({test_type}) finished.")
            print("\n--- Final LLM Output ---")
            print(output)

    if output is None:
        logger.warning(
            f"GraphUpdateAgent ({test_type}) did not produce final text, but may have run successfully."
        )

    logger.info(
        f"--- Finished Isolated GraphUpdateAgent Test ({test_type.upper()}) ---"
    )


if __name__ == "__main__":
    # Get test type from command line argument
    if len(sys.argv) != 2 or sys.argv[1] not in ["epic", "story", "issue"]:
        print("Usage: python test_GraphUpdateAgent.py <epic|story|issue>")
        sys.exit(1)

    test_type_arg = sys.argv[1]

    try:
        asyncio.run(run_graph_agent_test(test_type_arg))
        logger.info(f"GraphUpdateAgent test ({test_type_arg}) completed.")
    except Exception:
        logger.exception(f"GraphUpdateAgent test ({test_type_arg}) failed.")
