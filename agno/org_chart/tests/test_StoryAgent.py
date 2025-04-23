import json
import logging
import asyncio
import pathlib
from agno.agent import RunResponse

from models.schemas import StoryList
from utils.callbacks import log_agno_callbacks
from agents.StoryAgent import build_story_agent
from tools.tool_jira_epic_issues import jira_get_epic_issues
from utils.helpers import load_config, resolve_model


log = logging.getLogger(__name__)


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
    log.info("--- Starting Isolated Agno StoryAgent Test ---")

    # --- Load Input Data ---
    input_state_data = {}
    try:
        with open(INPUT_FILE, "r") as f:
            raw_input_data = json.load(f)
            input_state_data[INPUT_STATE_KEY] = json.dumps(raw_input_data, indent=2)
            log.info(
                f"Loaded input data from {INPUT_FILE} into state key '{INPUT_STATE_KEY}'."
            )
            log.debug(json.dumps(input_state_data, indent=2))
    except Exception as e:
        log.critical(f"Failed to load input file {INPUT_FILE}: {e}")
        raise

    # --- Agent Setup ---
    agent = build_story_agent(
        model=MODEL,
        tools=[jira_get_epic_issues],
        initial_state=input_state_data,
    )
    # Enable debugging during test development
    agent.debug_mode = True
    agent.show_tool_calls = True
    log.info(f"Built Agno StoryAgent using model {model_id}")

    # --- Run Agent ---
    trigger_message = "Get stories/tasks from Jira Epics"
    final_response: RunResponse = None

    log.info("Running StoryAgent...")
    try:
        # Use agent.arun for async execution, or agent.run for sync
        # Provide input state here
        response = await agent.arun(trigger_message, session_id=TEST_SESSION_ID)
        final_response = response
        run_label = "StoryAgentTest"
        log_agno_callbacks(final_response, run_label, filename=f"{run_label}_callbacks")

    except Exception as e:
        log.exception("StoryAgent execution failed.")
        raise
    finally:  # Print state even if an exception occurred mid-run
        if agent and hasattr(agent, "session_state"):
            log.debug("--- Agent's final internal session_state ---")
            log.debug(json.dumps(agent.session_state, indent=2))
            log.debug("--- End agent final state ---")

    # --- Save & Verify Output ---
    if final_response and final_response.content:
        log.info(f"Saving StoryAgent output to: {OUTPUT_FILE}")
        output_content = final_response.content

        # --- Verification ---
        assert isinstance(output_content, StoryList), (
            f"Expected output type StoryList, but got {type(output_content)}"
        )
        log.info(
            f"Output validation successful (type: StoryList). Found {len(output_content.stories)} stories."
        )

        try:
            # Save the validated Pydantic model data
            with open(OUTPUT_FILE, "w") as f:
                json.dump(output_content.model_dump(), f, indent=4)
                log.info(f"Saved structured output to {OUTPUT_FILE}")
        except IOError as e:
            log.error(f"Failed to write output file {OUTPUT_FILE}: {e}")

        # Handle case if content isn't a Pydantic model after all
        except AttributeError:
            log.error("Output content does not have model_dump method.")

            # Fallback: try saving raw content if content exists
            if not isinstance(output_content, StoryList):
                try:
                    with open(OUTPUT_FILE.with_suffix(".raw.json"), "w") as f:
                        json.dump(output_content, f, indent=4)
                except Exception:
                    log.error("Could not save raw output content.")

    else:
        log.error("StoryAgent did not produce a final response content.")
        assert False, "StoryAgent test failed: No final content."

    log.info("--- Finished Isolated Agno StoryAgent Test ---")


if __name__ == "__main__":
    try:
        asyncio.run(run_story_agent_test())
    except Exception:
        log.exception("StoryAgent test failed with unhandled exception.")
