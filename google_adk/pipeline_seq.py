import asyncio
import logging
from google.genai import types
from google.adk.runners import Runner
from google.adk.agents import SequentialAgent
from google.adk.sessions import InMemorySessionService

from google_adk.tests.debug_callbacks import save_trace_event
from google_adk.utils_adk import load_config, load_tools, resolve_model

from google_adk.agents.EpicAgent import build_epic_agent
from google_adk.agents.StoryAgent import build_story_agent
from google_adk.agents.IssueAgent import build_issue_agent
from google_adk.agents.GraphUpdateAgent import build_graph_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


model_provider = "openai"
RUNTIME_PARAMS = load_config("runtime")

# Session settings
APP_NAME = RUNTIME_PARAMS["SESSION"]["app_name"]
USER_ID = RUNTIME_PARAMS["SESSION"]["user_id"]
SESSION_ID = RUNTIME_PARAMS["SESSION"]["session_id"]
SEQ_SESSION_ID = f"{SESSION_ID}_sequential"

# LLM models
MODELS = RUNTIME_PARAMS["MODELS"][model_provider]
MODEL_EPIC = resolve_model(MODELS["epic"], provider=model_provider)
MODEL_STORY = resolve_model(MODELS["story"], provider=model_provider)
MODEL_ISSUE = resolve_model(MODELS["issue"], provider=model_provider)
MODEL_GRAPH = resolve_model(MODELS["graph"], provider=model_provider)

# Session state outputs (memory)
OUTPUTS = RUNTIME_PARAMS["OUTPUTS"]
EPIC_OUTPUTS = OUTPUTS["epic"]
STORY_OUTPUTS = OUTPUTS["story"]
ISSUE_OUTPUTS = OUTPUTS["issue"]
GRAPH_OUTPUTS = OUTPUTS["graph"]


# =======================================


# Main pipeline
async def main():
    jira_mcp, exit_stack, jira_custom, arango_custom = await load_tools()
    logger.info("Tools loaded.")

    # Initialize session service
    session_service = InMemorySessionService()

    # Clean up previous sequential run session
    try:
        session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SEQ_SESSION_ID
        )
        logger.info(f"Deleted existing sequential session: {SEQ_SESSION_ID}")
    except KeyError:
        logger.info(f"Sequential session {SEQ_SESSION_ID} did not exist, creating new.")
        pass

    # Create a new session for this run
    session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SEQ_SESSION_ID
    )
    logger.info(f"Created new sequential session: {SEQ_SESSION_ID}")

    # Compose pipeline
    logger.info("Composing SequentialAgent pipeline...")
    pipeline_agent = SequentialAgent(
        name="SequentialPipeline",
        sub_agents=[
            # 1. Fetch Epics (No input key needed)
            build_epic_agent(
                model=MODEL_EPIC,
                tools=jira_mcp,
                output_key=EPIC_OUTPUTS,
            ),
            # 2. Graph Epics (Reads list from EPIC_OUTPUTS)
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="epic_graph_prompt",
                tools=[arango_custom],
                input_key=EPIC_OUTPUTS,
                output_key=f"{GRAPH_OUTPUTS}_epics",
            ),
            # 3. Find Stories (Reads list from EPIC_OUTPUTS)
            build_story_agent(
                model=MODEL_STORY,
                tools=[jira_custom],
                input_key=EPIC_OUTPUTS,
                output_key=STORY_OUTPUTS,
            ),
            # 4. Graph Stories (Reads list from STORY_OUTPUTS)
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="story_graph_prompt",
                tools=[arango_custom],
                input_key=STORY_OUTPUTS,
                output_key=f"{GRAPH_OUTPUTS}_stories",
            ),
            # 5. Find Issues (Reads list from STORY_OUTPUTS)
            build_issue_agent(
                model=MODEL_ISSUE,
                tools=jira_mcp,
                input_key=STORY_OUTPUTS,
                output_key=ISSUE_OUTPUTS,
            ),
            # 6. Graph Issues (Reads list from ISSUE_OUTPUTS)
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="issue_graph_prompt",
                tools=[arango_custom],
                input_key=ISSUE_OUTPUTS,
                output_key=f"{GRAPH_OUTPUTS}_issues",
            ),
        ],
    )
    logger.info("SequentialAgent pipeline composed.")

    # --- Attach Runner ---
    runner = Runner(
        agent=pipeline_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    # --- Run the Pipeline ---
    # Initial user prompt starts the sequence, agents mainly act based on state
    user_prompt_content = types.Content(
        role="user", parts=[types.Part(text="Follow instructions.")]
    )
    logger.info("Running Sequential Pipeline...")

    final_response_text = "Pipeline did not complete with a final response."
    async with exit_stack:
        async for event in runner.run_async(
            user_id=USER_ID, session_id=SEQ_SESSION_ID, new_message=user_prompt_content
        ):
            save_trace_event(event, test_name="SequentialRun")

            # Capture final response from the LAST agent in the sequence
            if (
                event.is_final_response()
                and event.author == pipeline_agent.sub_agents[-1].name
            ):
                if event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text
                    logger.info(
                        f"Final response from pipeline (agent: {event.author}): {final_response_text}"
                    )
                else:
                    logger.info(
                        f"Final response event from pipeline (agent: {event.author}) but no content."
                    )

    logger.info("--- Sequential Pipeline Run Complete ---")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ValueError as ve:
        logger.critical(f"Pipeline stopped due to ValueError: {ve}")
        exit(1)
    except Exception as e:
        logger.exception(
            "An unhandled exception occurred during sequential pipeline execution."
        )
        exit(1)
