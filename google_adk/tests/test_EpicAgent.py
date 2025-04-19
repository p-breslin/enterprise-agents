import json
import logging
import asyncio
import pathlib
from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from debug_callbacks import trace_event
from google_adk.agents.EpicAgent import build_epic_agent
from google_adk.utils_adk import load_config, load_tools, extract_json, resolve_model


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# === Runtime params ===

RUNTIME_PARAMS = load_config("runtime")
APP_NAME = RUNTIME_PARAMS["SESSION"]["app_name"]
USER_ID = RUNTIME_PARAMS["SESSION"]["user_id"]
TEST_SESSION_ID = "test_session_epic_agent"

OUTPUTS = RUNTIME_PARAMS["OUTPUTS"]
AGENT_OUTPUT_KEY = OUTPUTS["epic"]

model_provider = "openai"
SELECTED_MODEL = RUNTIME_PARAMS["MODELS"][model_provider]["epic"]
MODEL = resolve_model(SELECTED_MODEL, provider=model_provider)

OUTPUT_DIR = pathlib.Path(__file__).parent / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)  # Create directory if it doesn't exist

model_save_name = SELECTED_MODEL.split("/")[-1]
OUTPUT_FILE = OUTPUT_DIR / f"epics_output_{model_save_name}.json"

# ======================


async def run_epic_agent_test():
    logger.info("--- Starting Isolated EpicAgent Test ---")
    jira_mcp, exit_stack, _, _ = await load_tools()
    logger.info("Tools loaded.")

    session_service = InMemorySessionService()
    try:
        session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=TEST_SESSION_ID
        )
        logger.info(f"Deleted existing session: {TEST_SESSION_ID}")
    except KeyError:
        logger.info(f"Session {TEST_SESSION_ID} not found, creating new.")
    session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=TEST_SESSION_ID
    )
    logger.info(f"Created session: {TEST_SESSION_ID}")

    # --- Agent Setup ---
    agent = build_epic_agent(
        model=MODEL,
        tools=jira_mcp,
        output_key=AGENT_OUTPUT_KEY,  # Agent saves its result here
    )
    logger.info(f"Built EpicAgent using model {model_save_name}")

    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    # --- Run Agent ---
    trigger_message = types.Content(role="user", parts=[types.Part(text="Get epics")])
    output = None

    logger.info("Running EpicAgent...")
    async with exit_stack:
        async for event in runner.run_async(
            user_id=USER_ID, session_id=TEST_SESSION_ID, new_message=trigger_message
        ):
            trace_event(event)
            if event.is_final_response() and event.content and event.content.parts:
                output = event.content.parts[0].text
                logger.info("EpicAgent finished.")
                print("\n--- Final LLM Output ---")
                print(output)

    # --- Save Output ---
    if output:
        logger.info(f"Saving EpicAgent output to: {OUTPUT_FILE}")
        try:
            structured_output = extract_json(raw_text=output, key="epics")
            with open(OUTPUT_FILE, "w") as f:
                json.dump(structured_output, f, indent=4)

        except IOError as e:
            logger.error(f"Failed to write output file {OUTPUT_FILE}: {e}")

    else:
        logger.error("EpicAgent did not produce a final response text.")

    logger.info("--- Finished Isolated EpicAgent Test ---")


if __name__ == "__main__":
    try:
        asyncio.run(run_epic_agent_test())
    except Exception:
        logger.exception("EpicAgent test failed with unhandled exception.")
