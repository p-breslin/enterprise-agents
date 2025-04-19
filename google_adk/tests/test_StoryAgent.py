import json
import asyncio
import logging
import pathlib
from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from debug_callbacks import trace_event
from google_adk.agents.StoryAgent import build_story_agent
from google_adk.utils_adk import extract_json, load_tools, load_config, resolve_model

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# === Runtime params ===

RUNTIME_PARAMS = load_config("runtime")
APP_NAME = RUNTIME_PARAMS["SESSION"]["app_name"]
USER_ID = RUNTIME_PARAMS["SESSION"]["user_id"]
TEST_SESSION_ID = "test_session_story_agent"

OUTPUTS = RUNTIME_PARAMS["OUTPUTS"]
AGENT_OUTPUT_KEY = OUTPUTS["story"]

model_provider = "google"
SELECTED_MODEL = RUNTIME_PARAMS["MODELS"][model_provider]["story"]
MODEL = resolve_model(SELECTED_MODEL, provider=model_provider)

# Define Input (epics data from EpicAgent)
INPUT_DIR = pathlib.Path(__file__).parent / "test_data"
INPUT_FILE = INPUT_DIR / "test_epic_data.json"
INPUT_STATE_KEY = "epic_data_input"  # Key the agent will read from state

OUTPUT_DIR = pathlib.Path(__file__).parent / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

model_save_name = SELECTED_MODEL.split("/")[-1]
OUTPUT_FILE = OUTPUT_DIR / f"stories_output_{model_save_name}.json"

# ======================


async def run_story_agent_test():
    logger.info("--- Starting Isolated StoryAgent Test ---")
    _, exit_stack, jira_custom, _ = await load_tools()
    logger.info("Tools loaded.")

    session_service = InMemorySessionService()
    try:
        session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=TEST_SESSION_ID
        )
        logger.info(f"Deleted existing session: {TEST_SESSION_ID}")
    except KeyError:
        logger.info(f"Session {TEST_SESSION_ID} not found, creating new.")
    session = session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=TEST_SESSION_ID
    )
    logger.info(f"Created session: {TEST_SESSION_ID}")

    # Load input data and put it into state
    try:
        with open(INPUT_FILE, "r") as f:
            data = json.load(f)
        session.state[INPUT_STATE_KEY] = json.dumps(data)
    except Exception as e:
        logger.critical(f"Failed to load or process input file {INPUT_FILE}: {e}")
        raise

    # --- Agent Setup ---
    agent = build_story_agent(
        model=MODEL,
        tools=[jira_custom],
        input_key=INPUT_STATE_KEY,  # Tell agent where to read data
        output_key=AGENT_OUTPUT_KEY,  # Agent saves its result here
    )
    logger.info(f"Built StoryAgent using model {model_save_name}")

    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    # --- Run Agent ---
    trigger_message = types.Content(
        role="user", parts=[types.Part(text="Find stories based on input state")]
    )
    output = None

    logger.info("Running StoryAgent...")
    async with exit_stack:
        async for event in runner.run_async(
            user_id=USER_ID, session_id=TEST_SESSION_ID, new_message=trigger_message
        ):
            trace_event(event)
            if event.is_final_response() and event.content and event.content.parts:
                output = event.content.parts[0].text
                logger.info("StoryAgent finished.")
                print("\n--- Final LLM Output ---")
                print(output)

    # --- Save Output ---
    if output:
        logger.info(f"Saving StoryAgent output to: {OUTPUT_FILE}")
        try:
            structured_output = extract_json(raw_text=output, key="stories")
            with open(OUTPUT_FILE, "w") as f:
                json.dump(structured_output, f, indent=4)

        except IOError as e:
            logger.error(f"Failed to write output file {OUTPUT_FILE}: {e}")

    else:
        logger.error("EpicAgent did not produce a final response text.")

    logger.info("--- Finished Isolated StoryAgent Test ---")


if __name__ == "__main__":
    try:
        asyncio.run(run_story_agent_test())
    except Exception:
        logger.exception("StoryAgent test failed with unhandled exception.")
