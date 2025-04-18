"""
Jira-ArangoDB Multi-Agent Pipeline (Google ADK)
-------------------------------------------------

This pipeline ingests Jira data and incrementally populates an ArangoDB knowledge graph.

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


# ONLY ITEM TO CHANGE
model_provider = "openai"


# ========================================
# Runtime parameters (do not change)
# ========================================

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

# ========================================


async def main():
    # Load tools
    jira_mcp, exit_stack, jira_custom, arango_custom = await load_tools()

    # Initialize session service
    session_service = InMemorySessionService()

    # Good practice to start fresh or retrieve existing session carefully
    try:
        session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        print(f"Deleted existing session: {SESSION_ID}")
    except KeyError:
        print(f"Session {SESSION_ID} did not exist, creating new.")
        pass

    # Create a new session
    session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )

    # === Stage 1: Run Epic Agent ===
    epic_agent = build_epic_agent(
        model=MODEL_EPIC, tools=jira_mcp, output_key=EPIC_OUTPUTS
    )
    epic_runner = Runner(
        agent=epic_agent, app_name=APP_NAME, session_service=session_service
    )
    content = types.Content(role="user", parts=[types.Part(text="Get epics")])

    epic_data = None
    async with exit_stack:
        print("Running Stage 1: Epic discovery...")
        async for event in epic_runner.run_async(
            user_id=USER_ID, session_id=SESSION_ID, new_message=content
        ):
            save_trace_event(event, "Stage 1")
            if event.is_final_response() and event.content and event.content.parts:
                epic_data = extract_json(event.content.parts[0].text, key="epics")

    if not epic_data:
        raise ValueError("No epics returned.")

    # === Stage 2: Process Epics ===
    agents = []
    story_output_keys = []

    # Run on an Epic item-by-item basis
    for i, epic_item in enumerate(epic_data):
        # output_key will determine where LLM output is saved in session state
        # unique keys to avoid overwriting the session state

        epic_input_key = f"{EPIC_OUTPUTS}_{i}"
        graph_output_key = f"{GRAPH_OUTPUTS}_{i}"
        story_output_key = f"{STORY_OUTPUTS}_{i}"

        # Re-fetch the full Session object when modifying session state
        session = session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        session.state[epic_input_key] = (
            json.dumps(epic_item) if not isinstance(epic_item, str) else epic_item
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
    print("Running Stage 2: Epic graphing and story discovery...")
    await run_parallel(STAGE2, agents, APP_NAME, USER_ID, SESSION_ID, session_service)

    # === Stage 3: Process Stories ===
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
    print("Running Stage 3: Story graphing and issue discovery...")
    await run_parallel(STAGE3, agents, APP_NAME, USER_ID, SESSION_ID, session_service)

    # === Stage 4: Process Issues ===
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
    print("Running Stage 4: Issue graphing...")
    await run_parallel(STAGE4, agents, APP_NAME, USER_ID, SESSION_ID, session_service)

    print("Pipeline complete.")


async def run_parallel(name, agents, app_name, user_id, session_id, session_service):
    if not agents:
        print(f"No agents to run for stage: {name}")
        return
    runner = Runner(
        agent=ParallelAgent(name=name, sub_agents=agents),
        app_name=app_name,
        session_service=session_service,
    )

    dummy_message = types.Content(role="user", parts=[types.Part(text="run")])
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=dummy_message
    ):
        save_trace_event(event, name)
        if event.is_final_response() and event.content and event.content.parts:
            print(f"[{name}] Final response.")


def get_data_from_memory(output_keys, state, label):
    """
    Helper function for getting data from memory in a safe way in case any intermediate LLM calls fail.
    """
    data = []
    for key in output_keys:
        raw = state.get(key, "[]")
        try:
            data.extend(extract_json(raw, key=label))
        except Exception as e:
            print(f"Failed to parse {label} output at {key}: {e}")

    if not data:
        raise ValueError(f"No {label} data found.")
    return data


if __name__ == "__main__":
    asyncio.run(main())
