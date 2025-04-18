"""
Jira-ArangoDB Multi-Agent Pipeline (Google ADK)
-------------------------------------------------

This pipeline ingests Jira data and incrementally populates an ArangoDB knowledge graph (KG).

Flow Overview:
---------------
Stage 1:
- Run EpicAgent to retrieve epics.

Stage 2:
- Split Epic data into parts. Distribute among multiple instances of:
    A. GraphUpdateAgent (to update graph with Epic data)
    B. StoryAgent (to retrieve stories)
- Note that A. and B. are executed concurrently inside a ParallelAgent block.

Stage 3:
- Split Story data into parts. Distribute among multiple instances of:
    A. GraphUpdateAgent (to update graph with Story data)
    B. IssueAgent (to retrieve story metadata)
- Note that A. and B. are executed concurrently inside a ParallelAgent block.

Stage 4:
- Split Story data into parts. Distribute among multiple instances of:
    A. GraphUpdateAgent (to update graph with Issue data)
- Note that A. is executed concurrently inside a ParallelAgent block.

Tooling Notes:
---------------
- EpicAgent and IssueAgent use MCP tools.
- StoryAgent and GraphUpdateAgent use custom function tools.
"""

import json
import asyncio
import logging
from google.genai import types

from google.adk.runners import Runner
from google.adk.agents import ParallelAgent
from google.adk.sessions import InMemorySessionService

from google_adk.tests.debug_callbacks import save_trace_event
from google_adk.utils_adk import load_config, extract_json, resolve_model, load_tools

from google_adk.agents.EpicAgent import build_epic_agent
from google_adk.agents.StoryAgent import build_story_agent
from google_adk.agents.IssueAgent import build_issue_agent
from google_adk.agents.GraphUpdateAgent import build_graph_agent

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ==============================
# Settings to configure manually
# ==============================
model_provider = "openai"


# ==================================
# Runtime parameters (do not change)
# ==================================
RUNTIME_PARAMS = load_config("runtime")

# Session settings
APP_NAME = RUNTIME_PARAMS["SESSION"]["app_name"]
USER_ID = RUNTIME_PARAMS["SESSION"]["user_id"]
SESSION_ID = RUNTIME_PARAMS["SESSION"]["session_id"]

# LLM models
MODELS = RUNTIME_PARAMS["MODELS"][model_provider]
MODEL_EPIC = resolve_model(MODELS["epic"], provider=model_provider)
MODEL_STORY = resolve_model(MODELS["story"], provider=model_provider)
MODEL_ISSUE = resolve_model(MODELS["issue"], provider=model_provider)
MODEL_GRAPH = resolve_model(MODELS["graph"], provider=model_provider)

# Naming conventions
NAMES = RUNTIME_PARAMS["AGENT_NAMES"]
STAGE2 = NAMES["stage2"]
STAGE3 = NAMES["stage3"]
STAGE4 = NAMES["stage4"]

# Session state outputs (memory)
OUTPUTS = RUNTIME_PARAMS["OUTPUTS"]
EPIC_OUTPUTS = OUTPUTS["epic"]
STORY_OUTPUTS = OUTPUTS["story"]
ISSUE_OUTPUTS = OUTPUTS["issue"]
GRAPH_OUTPUTS = OUTPUTS["graph"]


# =============
# Main pipeline
# =============
async def main():
    # Load tools
    jira_mcp, exit_stack, jira_custom, arango_custom = await load_tools()
    logger.info("Tools loaded.")

    # Initialize session service
    session_service = InMemorySessionService()

    # Good practice to start fresh or retrieve existing session carefully
    try:
        session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        logger.info(f"Deleted existing session: {SESSION_ID}")
    except KeyError:
        logger.info(f"Session {SESSION_ID} did not exist, creating new.")
        pass

    # Create a new session
    session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    logger.info(f"Created new session: {SESSION_ID}")

    # =====================================
    # Stage 1: Collect Epics with EpicAgent
    # =====================================
    logger.info("--- Stage 1: Collecting Jira Epics ---")
    epic_agent = build_epic_agent(
        model=MODEL_EPIC, tools=jira_mcp, output_key=EPIC_OUTPUTS
    )
    epic_runner = Runner(
        agent=epic_agent, app_name=APP_NAME, session_service=session_service
    )
    content = types.Content(role="user", parts=[types.Part(text="Get epics")])

    epic_data = None
    async with exit_stack:
        async for event in epic_runner.run_async(
            user_id=USER_ID, session_id=SESSION_ID, new_message=content
        ):
            save_trace_event(event, "Stage 1")
            if event.is_final_response() and event.content and event.content.parts:
                result = event.content.parts[0].text
                logger.info("[Stage 1] Final response received from EpicAgent.")

                try:
                    epic_data = extract_json(result, key="epics")
                    logger.debug(f"[Stage 1] Extracted {len(epic_data)} epics.")
                except Exception as e:
                    logger.error(
                        f"[Stage 1] Failed to extract epics from final response: {e}",
                        exc_info=False,
                    )
                    logger.debug(f"[Stage 1] Raw Response: {result}")

    if not epic_data:
        logger.critical("No epics returned from Stage 1. Terminating pipeline.")
        raise ValueError("No epics returned.")

    # =================================================================
    # Stage 2: Update KG with Epics and collect Stories with StoryAgent
    # =================================================================
    logger.info("--- Stage 2: Update KG with Epics and Collect Stories ---")
    agents = []
    story_output_keys = []

    # Re-fetch the full Session object for modifying session state
    session = session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )

    # Run on an Epic item-by-item basis
    for i, epic_item in enumerate(epic_data):
        # output_key will determine where LLM output is saved in session state
        # unique keys to avoid overwriting the session state

        epic_input_key = f"{EPIC_OUTPUTS}_{i}"
        graph_output_key = f"{GRAPH_OUTPUTS}_{i}"
        story_output_key = f"{STORY_OUTPUTS}_{i}"

        # Write to session.state
        session.state[epic_input_key] = (
            json.dumps(epic_item) if not isinstance(epic_item, str) else epic_item
        )
        logger.debug(
            f"[Stage 2] Placed epic {i} into state key '{epic_input_key}'. Epic data item:\n{epic_item}"
        )

        # Create an instance of GraphUpdateAgent to add the Epic item to graph
        agents.append(
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="epic_graph_prompt",
                tools=[arango_custom],
                input_key=epic_input_key,
                output_key=graph_output_key,
            )
        )

        # Create an instance of StoryAgent to find stories for the Epic item
        agents.append(
            build_story_agent(
                model=MODEL_STORY,
                tools=[jira_custom],
                input_key=epic_input_key,
                output_key=story_output_key,
            )
        )

        # Keep track of the expected output keys
        story_output_keys.append(story_output_key)

    # Create a concurrent process
    await run_parallel(STAGE2, agents, APP_NAME, USER_ID, SESSION_ID, session_service)

    # ===================================================================
    # Stage 3: Update KG with Stories and collect Issues with IssueAgent
    # ===================================================================
    logger.info("--- Stage 3: Update KG with Stories and Collect Issues ---")
    agents = []
    issue_output_keys = []

    # Refresh session state view
    session = session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    story_data = get_data_from_memory(
        output_keys=story_output_keys, state=session.state, label="stories"
    )

    # Run on an Story item-by-item basis
    for i, story_item in enumerate(story_data):
        story_input_key = f"{STORY_OUTPUTS}_{i}"
        graph_output_key = f"{GRAPH_OUTPUTS}_{i}"
        issue_output_key = f"{ISSUE_OUTPUTS}_{i}"

        # Write to session.state
        session.state[story_input_key] = (
            json.dumps(story_item) if not isinstance(story_item, str) else story_item
        )
        logger.debug(
            f"[Stage 3] Placed story {i} into state key '{story_input_key}'. Story data item:\n{story_item}"
        )

        # Create an instance of GraphUpdateAgent to add the Story item to graph
        agents.append(
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="story_graph_prompt",
                tools=[arango_custom],
                input_key=story_input_key,
                output_key=graph_output_key,
            )
        )

        # Create an instance of IssueAgent to find metadata for the Story item
        agents.append(
            build_issue_agent(
                model=MODEL_ISSUE,
                tools=jira_mcp,
                input_key=story_input_key,
                output_key=issue_output_key,
            )
        )

        # Keep track of the expected output keys
        issue_output_keys.append(issue_output_key)

    # Create a concurrent process
    await run_parallel(STAGE3, agents, APP_NAME, USER_ID, SESSION_ID, session_service)

    # ==============================
    # Stage 4: Update KG with Issues
    # ==============================
    agents = []

    # Refresh session state view
    session = session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    issue_data = get_data_from_memory(
        output_keys=issue_output_keys, state=session.state, label="issues"
    )

    # Run on an Issue item-by-item basis
    for i, issue_item in enumerate(issue_data):
        issue_input_key = f"{ISSUE_OUTPUTS}_{i}"
        graph_output_key = f"{GRAPH_OUTPUTS}_{i}"

        # Write to session.state
        session.state[issue_input_key] = (
            json.dumps(issue_item) if not isinstance(issue_item, str) else issue_item
        )
        logger.debug(
            f"[Stage 4] Placed issue {i} into state key '{issue_input_key}'. Issue data item:\n{issue_item}"
        )

        # Create an instance of GraphUpdateAgent to add the Issue item to graph
        agents.append(
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="issue_graph_prompt",
                tools=[arango_custom],
                input_key=issue_input_key,
                output_key=graph_output_key,
            )
        )

    # Create a concurrent process
    await run_parallel(STAGE4, agents, APP_NAME, USER_ID, SESSION_ID, session_service)

    print("Pipeline complete.")


async def run_parallel(name, agents, app_name, user_id, session_id, session_service):
    """
    Creates and runs a ParallelAgent instance for running concurrent processes.
    """
    logger.info(f"[{name}] Creating ParallelAgent with {len(agents)} sub-agents")
    runner = Runner(
        agent=ParallelAgent(name=name, sub_agents=agents),
        app_name=app_name,
        session_service=session_service,
    )

    # Trigger the parallel execution
    dummy_message = types.Content(
        role="user", parts=[types.Part(text="Follow instructions.")]
    )
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=dummy_message
    ):
        save_trace_event(event, name)
        if event.is_final_response():
            logger.info(f"[{name}] Final event received from ParallelAgent.")


def get_data_from_memory(output_keys, state, label):
    """
    Helper function for getting data from memory in a safe way in case any intermediate LLM calls fail. Assumes data in state is a JSON string and extracts the list associated with the 'label' key from within that JSON.
    """
    data = []
    for key in output_keys:
        raw = state.get(key)
        if not raw:
            logger.warning(f"No data found in state for key '{key}'. Skipping.")
            continue
        try:
            data.extend(extract_json(raw, key=label))
        except Exception as e:
            logger.warning(f"Failed to parse {label} output at {key}: {e}")
            logger.debug(f"Raw data snippet: {raw[:200]}...")

    if not data:
        raise ValueError(f"Fatal error: no {label} data found.")
    return data


if __name__ == "__main__":
    asyncio.run(main())
