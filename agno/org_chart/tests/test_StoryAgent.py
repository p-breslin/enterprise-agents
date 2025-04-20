import json
import logging
import asyncio
import pathlib
from agno.agent import RunResponse

from schemas import StoryList
from callbacks import print_callbacks
from agents.StoryAgent import build_story_agent
from tools.tool_jira_search import jira_get_epic_issues
from utils_agno import load_config, resolve_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)


# === Runtime params ===
runtime_params = load_config("runtime")
TEST_SESSION_ID = "test_session_story_agent_agno"

model_provider = "openai"
model_id = runtime_params["MODELS"][model_provider]["story"]
MODEL = resolve_model(provider=model_provider, model_id=model_id)

# Define Input (epics data from EpicAgent)
input_dir = pathlib.Path(__file__).parent / "test_data"
INPUT_FILE = input_dir / "test_epic_data.json"
INPUT_STATE_KEY = "epics_data_input"  # MUST match StoryAgent's prompt template

output_dir = pathlib.Path(__file__).parent / "test_output"
output_dir.mkdir(exist_ok=True)
OUTPUT_FILE = output_dir / f"story_output_{model_id}.json"
# ======================


async def run_story_agent_test():
    logger.info("--- Starting Isolated Agno StoryAgent Test ---")

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
    agent = build_story_agent(
        model=MODEL,
        tools=[jira_get_epic_issues],
        input_state_key=INPUT_STATE_KEY,  # Pass the key name to the builder
    )
    # Enable debugging during test development
    agent.debug_mode = True
    agent.show_tool_calls = True
    logger.info(f"Built Agno StoryAgent using model {model_id}")

    # --- Run Agent ---
    trigger_message = "Get stories/tasks from Jira Epics"
    final_response: RunResponse = None

    logger.info("Running StoryAgent...")
    try:
        # Use agent.arun for async execution, or agent.run for sync
        # Provide input state here
        response = await agent.arun(
            trigger_message, session_id=TEST_SESSION_ID, session_state=input_state_data
        )
        final_response = response
        print_callbacks(final_response, "StoryAgentTest")

    except Exception as e:
        logger.exception("StoryAgent execution failed.")
        raise

    # --- Save & Verify Output ---
    if final_response and final_response.content:
        logger.info(f"Saving StoryAgent output to: {OUTPUT_FILE}")
        output_content = final_response.content

        # --- Verification ---
        assert isinstance(output_content, StoryList), (
            f"Expected output type StoryList, but got {type(output_content)}"
        )
        logger.info(
            f"Output validation successful (type: StoryList). Found {len(output_content.stories)} stories."
        )

        try:
            # Save the validated Pydantic model data
            with open(OUTPUT_FILE, "w") as f:
                json.dump(output_content.model_dump(), f, indent=4)
                logger.info(f"Saved structured output to {OUTPUT_FILE}")
        except IOError as e:
            logger.error(f"Failed to write output file {OUTPUT_FILE}: {e}")

        # Handle case if content isn't a Pydantic model after all
        except AttributeError:
            logger.error("Output content does not have model_dump method.")

            # Fallback: try saving raw content if content exists
            if not isinstance(output_content, StoryList):
                try:
                    with open(OUTPUT_FILE.with_suffix(".raw.json"), "w") as f:
                        json.dump(output_content, f, indent=4)
                except Exception:
                    logger.error("Could not save raw output content.")

    else:
        logger.error("StoryAgent did not produce a final response content.")
        assert False, "StoryAgent test failed: No final content."

    logger.info("--- Finished Isolated Agno StoryAgent Test ---")


if __name__ == "__main__":
    try:
        asyncio.run(run_story_agent_test())
    except Exception:
        logger.exception("StoryAgent test failed with unhandled exception.")
