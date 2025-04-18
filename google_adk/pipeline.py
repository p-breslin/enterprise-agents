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
from google.adk.tools.function_tool import FunctionTool
from google.adk.sessions import InMemorySessionService

from google_adk.tools.mcps import jira_mcp_tools
from google_adk.tests.debug_callbacks import save_trace_event
from google_adk.tools.ArangoUpsertTool import arango_upsert
from google_adk.tools.custom_tools import jira_get_epic_issues
from google_adk.utils_adk import load_config, extract_json, resolve_model

from google_adk.agents.EpicAgent import build_epic_agent
from google_adk.agents.StoryAgent import build_story_agent
from google_adk.agents.IssueAgent import build_issue_agent
from google_adk.agents.GraphUpdateAgent import build_graph_agent

# Change this
model_provider = "openai"

# Runtime parameters from configuration file
RUNTIME_PARAMS = load_config("runtime")

MODELS = RUNTIME_PARAMS["MODELS"][model_provider]
MODEL_EPIC = resolve_model(MODELS["epic"], provider=model_provider)
MODEL_STORY = resolve_model(MODELS["story"], provider=model_provider)
MODEL_ISSUE = resolve_model(MODELS["issue"], provider=model_provider)
MODEL_GRAPH = resolve_model(MODELS["graph"], provider=model_provider)

NAMES = RUNTIME_PARAMS["AGENT_NAMES"]
STAGE2 = NAMES["stage2"]
STAGE3 = NAMES["stage3"]
STAGE4 = NAMES["stage4"]


async def main():
    jira_mcp, exit_stack, jira_custom, arango_custom = await load_tools()
    session_service = InMemorySessionService()
    app_name = RUNTIME_PARAMS["SESSION"]["app_name"]
    user_id = RUNTIME_PARAMS["SESSION"]["user_id"]
    session_id = RUNTIME_PARAMS["SESSION"]["session_id"]

    # Create a new session
    session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    # Obtain session state
    state = session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    ).state

    # === Stage 1: Run Epic Agent ===
    epic_agent = build_epic_agent(model=MODEL_EPIC, tools=jira_mcp)
    epic_runner = Runner(
        agent=epic_agent, app_name=app_name, session_service=session_service
    )
    content = types.Content(role="user", parts=[types.Part(text="Get epics")])

    epic_data = None
    async with exit_stack:
        print("Running Stage 1: Epic discovery...")
        async for event in epic_runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
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
    for i, epic in enumerate(epic_data):
        input_key = f"epic_input_{i}"
        output_key_story = f"story_output_{i}"

        # Add individual Epic item to session memory
        state[input_key] = json.dumps(epic)

        # Create an instance of GraphUpdateAgent to add the Epic item to graph
        agents.append(
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="epic_graph_prompt",
                tools=[arango_custom],
                data=epic,
            )
        )

        # Create an instance of StoryAgent to find stories for the Epic item
        agents.append(
            build_story_agent(model=MODEL_STORY, tools=[jira_custom], data=epic)
        )

        # Keep track of the expected output keys
        story_output_keys.append(output_key_story)

    # Create a concurrent process
    print("Running Stage 2: Epic graphing and story discovery...")
    await run_parallel(STAGE2, agents, app_name, user_id, session_id, session_service)

    # === Stage 3: Process Stories ===
    agents = []
    issue_output_keys = []
    story_data = get_data_from_memory(
        output_keys=story_output_keys, state=state, label="story"
    )

    # Run on an Story item-by-item basis
    for i, story in enumerate(story_data):
        input_key = f"story_input_{i}"
        output_key_issue = f"issue_output_{i}"

        # Add individual Story item to session memory
        state[input_key] = json.dumps(story)

        # Create an instance of GraphUpdateAgent to add the Story item to graph
        agents.append(
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="story_graph_prompt",
                tools=[arango_custom],
                data=story,
            )
        )

        # Create an instance of IssueAgent to find metadata for the Story item
        agents.append(build_issue_agent(model=MODEL_ISSUE, tools=jira_mcp, data=story))

        # Keep track of the expected output keys
        issue_output_keys.append(output_key_issue)

    # Create a concurrent process
    print("Running Stage 3: Story graphing and issue discovery...")
    await run_parallel(STAGE3, agents, app_name, user_id, session_id, session_service)

    # === Stage 4: Process Issues ===
    agents = []
    issue_data = get_data_from_memory(
        output_keys=issue_output_keys, state=state, label="issue"
    )

    # Run on an Issue item-by-item basis
    for i, issue in enumerate(issue_data):
        input_key = f"issue_input_{i}"

        # Add individual Issue item to session memory
        state[input_key] = json.dumps(issue)

        # Create an instance of GraphUpdateAgent to add the Issue item to graph
        agents.append(
            build_graph_agent(
                model=MODEL_GRAPH,
                prompt="issue_graph_prompt",
                tools=[arango_custom],
                data=issue,
            )
        )

    # Create a concurrent process
    print("Running Stage 4: Issue graphing...")
    await run_parallel(STAGE4, agents, app_name, user_id, session_id, session_service)

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


async def load_tools():
    jira_mcp, exit_stack = await jira_mcp_tools()
    jira_custom = FunctionTool(jira_get_epic_issues)
    arango_custom = FunctionTool(arango_upsert)
    return jira_mcp, exit_stack, jira_custom, arango_custom


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
