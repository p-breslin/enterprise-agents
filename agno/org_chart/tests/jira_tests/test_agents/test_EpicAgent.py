import json
import logging
import asyncio
import pathlib
from agno.agent import RunResponse

from agents import build_epic_agent
from models.schemas import EpicList
from utils.callbacks import log_agno_callbacks
from tools.tool_jira_search import jira_search
from utils.helpers import load_config, resolve_model


log = logging.getLogger(__name__)


# === Runtime params ===
runtime_params = load_config("runtime")
TEST_SESSION_ID = "test_session_epic_agent_agno"

model_provider = "openai"
model_id = runtime_params["MODELS"][model_provider]["epic"]
MODEL = resolve_model(provider=model_provider, model_id=model_id)

output_dir = pathlib.Path(__file__).parent / "../test_output"
output_dir.mkdir(exist_ok=True)
OUTPUT_FILE = output_dir / f"epic_output_{model_id}.json"
# ======================


async def run_epic_agent_test():
    log.info("--- Starting Isolated Agno EpicAgent Test ---")

    # --- Agent Setup ---
    agent = build_epic_agent(
        model=MODEL,
        tools=[jira_search],
    )
    # Enable debugging during test development
    agent.debug_mode = True
    agent.show_tool_calls = True
    log.info(f"Built Agno EpicAgent using model {model_id}")

    # --- Run Agent ---
    trigger_message = "Get epics"  # Simple trigger based on agent instructions
    final_response: RunResponse = None

    log.info("Running EpicAgent...")
    try:
        # Use agent.arun for async execution, or agent.run for sync
        # Pass session_id for tracking/state if needed later
        response = await agent.arun(trigger_message, session_id=TEST_SESSION_ID)
        final_response = response  # Since it's not streaming
        run_label = "EpicAgentTest"
        log_agno_callbacks(final_response, run_label, filename=f"{run_label}_callbacks")
    except Exception as e:
        log.exception("EpicAgent execution failed.")
        raise

    # --- Save & Verify Output ---
    if final_response and final_response.content:
        log.info(f"Saving EpicAgent output to: {OUTPUT_FILE}")
        output_content = final_response.content

        # --- Verification ---
        assert isinstance(output_content, EpicList), (
            f"Expected output type EpicList, but got {type(output_content)}"
        )
        log.info(
            f"Output validation successful (type: EpicList). Found {len(output_content.epics)} epics."
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
            if not isinstance(output_content, EpicList):
                try:
                    with open(OUTPUT_FILE.with_suffix(".raw.json"), "w") as f:
                        json.dump(output_content, f, indent=4)
                except Exception:
                    log.error("Could not save raw output content.")

    else:
        log.error("EpicAgent did not produce a final response content.")
        assert False, "EpicAgent test failed: No final content."

    log.info("--- Finished Isolated Agno EpicAgent Test ---")


if __name__ == "__main__":
    try:
        asyncio.run(run_epic_agent_test())
    except Exception:
        log.exception("EpicAgent test failed with unhandled exception.")
