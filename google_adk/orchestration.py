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
from google.genai import types

from google.adk.runners import Runner
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.function_tool import FunctionTool
from google.adk.sessions import InMemorySessionService
from google.adk.agents import SequentialAgent, ParallelAgent

from google_adk.tools.mcps import jira_mcp_tools
from google_adk.utils_adk import load_config, extract_json
from google_adk.tools.ArangoUpsertTool import arango_upsert
from google_adk.tools.custom_tools import jira_get_epic_issues
from google_adk.agents import (
    build_epic_agent,
    build_story_agent,
    build_issue_agent,
    build_graph_agent,
)


# Load model config
MODELS = load_config("runtime")["models"]["google"]


# Load tools
async def load_tools():
    jira_mcp, exit_stack = await jira_mcp_tools()
    jira_custom = FunctionTool(jira_get_epic_issues)
    arango_custom = FunctionTool(arango_upsert)
    return jira_mcp, exit_stack, jira_custom, arango_custom


async def create_pipeline():
    jira_mcp, exit_stack, jira_custom, arango_custom = await load_tools()

    session_service = InMemorySessionService()
    app_name = "jira_graph"
    user_id = "admin"
    session_id = "pipeline_run"

    # === Stage 1: Obtain Jira Epics ===
    epic_agent = build_epic_agent(
        model=MODELS["epic"], tools=jira_mcp, output_key="epic_list"
    )
    epic_runner = Runner(
        agent=epic_agent, app_name=app_name, session_service=session_service
    )
    session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    content = types.Content(role="user", parts=[types.Part(text="Get epics")])

    epic_data = []
    async with exit_stack:
        async for event in epic_runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            if event.is_final_response():
                epic_data = extract_json(
                    raw_text=event.content.parts[0].text, key="epics"
                )

    # === Stage 2: Process Epics ===
    graph_agents = []
    story_agents = []

    # Run on an Epic item-by-item basis
    for i, epic in enumerate(epic_data):
        input_key = f"epic_input_{i}"

        # Add individual Epic item to session memory
        session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        ).state[input_key] = json.dumps(epic)

        # Create an instance of GraphUpdateAgent to add the Epic item to graph
        graph_ag = build_graph_agent(
            model=MODELS["graph"],
            prompt="epic_graph_prompt",
            tools=[arango_custom],
            input_key=input_key,
            output_key=f"epic_graph_{i}",
        )

        # Create an instance of StoryAgent to find stories for the Epic item
        story_ag = build_story_agent(
            model=MODELS["story"],
            tools=jira_custom,
            input_key=input_key,
            output_key=f"story_output_{i}",
        )

        # Make into AgentTools to label and attach them to the pipeline
        graph_agents.append(AgentTool(agent=graph_ag, name=f"GraphAgent_{i}"))
        story_agents.append(AgentTool(agent=story_ag, name=f"StoryAgent_{i}"))

    # Create a concurrent process
    parallel_epic_processing = ParallelAgent(
        name="process_epics", sub_agents=graph_agents + story_agents
    )

    # === Stage 3: Process Stories ===
    story_data = []
    graph_agents = []
    issue_agents = []

    # Outputs from StoryAgent instances will be of varying length
    for i in range(len(story_agents)):
        story_output = session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        ).state.get(f"story_output_{i}", "[]")

        # Add JSON structure to the text response and add to flattened list
        story_output = extract_json(raw_text=story_output, key="stories")
        story_data.extend(story_output)

    # Run on an Story item-by-item basis
    for i, story in enumerate(story_data):
        input_key = f"story_input_{i}"

        # Add individual Story item to session memory
        session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        ).state[input_key] = json.dumps(story)

        # Create an instance of GraphUpdateAgent to add the Story item to graph
        graph_ag = build_graph_agent(
            model=MODELS["graph"],
            prompt="story_graph_prompt",
            tools=[arango_custom],
            input_key=input_key,
            output_key=f"story_graph_{i}",
        )

        # Create an instance of IssueAgent to find metadata for the Story item
        issue_ag = build_issue_agent(
            model=MODELS["issue"],
            tools=jira_mcp,
            input_key=input_key,
            output_key=f"issue_output_{i}",
        )

        # Make into AgentTools to label and attach them to the pipeline
        graph_agents.append(AgentTool(agent=graph_ag, name=f"GraphAgent_{i}"))
        issue_agents.append(AgentTool(agent=issue_ag, name=f"IssueAgent_{i}"))

    # Create a concurrent process
    parallel_story_processing = ParallelAgent(
        name="process_stories", sub_agents=graph_agents + issue_agents
    )

    # === Stage 4: Process Issues ===
    issue_data = []
    graph_agents = []

    # Outputs from IssueAgent instances will be of varying length
    for i in range(len(issue_agents)):
        issue_output = session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        ).state.get(f"issue_output_{i}", "[]")

        # Add JSON structure to the text response and add to flattened list
        issue_output = extract_json(raw_text=issue_output, key="issues")
        issue_data.extend(issue_output)

    # Run on an Issue item-by-item basis
    for i, issue in enumerate(issue_data):
        input_key = f"issue_input_{i}"

        # Add individual Issue item to session memory
        session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        ).state[input_key] = json.dumps(issue)

        # Create an instance of GraphUpdateAgent to add the Issue item to graph
        graph_ag = build_graph_agent(
            model=MODELS["graph"],
            prompt="issue_graph_prompt",
            tools=[arango_custom],
            input_key=input_key,
            output_key=f"issue_graph_{i}",
        )

        # Make into AgentTools to label and attach them to the pipeline
        graph_agents.append(AgentTool(agent=graph_ag, name=f"GraphAgent_{i}"))

    # Create a concurrent process
    parallel_issue_processing = ParallelAgent(
        name="process_issues", sub_agents=graph_agents
    )

    # === Full Sequential-Parallel Hybird Pipeline ===
    pipeline = SequentialAgent(
        name="JiraGraphPipeline",
        sub_agents=[
            epic_agent,
            parallel_epic_processing,
            parallel_story_processing,
            parallel_issue_processing,
        ],
    )

    return pipeline, exit_stack
