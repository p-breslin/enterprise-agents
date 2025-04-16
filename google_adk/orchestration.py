"""
Jira + ArangoDB Multi-Agent Integration Pipeline
------------------------------------------------

This script defines a hybrid sequential + parallel agent workflow using Google ADK.

Goal:
To extract Jira work item data (Epics → Stories → Issues) and incrementally populate an ArangoDB knowledge graph using a modular, multi-agent system.

Workflow:
----------

Stage 1: Discover Epics
  - EpicAgent queries Jira (via MCP tools) to retrieve epics.
  - Each epic is sent to a GraphUpdateAgent instance to upsert it into ArangoDB.

Stage 2: Discover Stories
  - For each epic, a parallel StoryAgent instance queries Jira (via FunctionTool) to get stories.
  - Each story is passed to a GraphUpdateAgent to upsert into ArangoDB.

Stage 3: Discover Issues
  - For each story, a parallel IssuesAgent (with MCP tools) fetches detailed metadata.
  - Each issue is passed to a GraphUpdateAgent for ingestion into ArangoDB.

Tooling:
---------
- Jira tools come from an MCP server and must be passed to agents that require them.
- StoryAgent and GraphUpdateAgent use custom tools wrapped in FunctionTool:
    - `jira_get_epic_issues` (custom function)
    - `arango_upsert` (custom ArangoDB utility)
"""

from google.genai import types
from google.adk.tools.function_tool import FunctionTool
from google.adk.agents import SequentialAgent, ParallelAgent

from google_adk.agents import (
    build_epic_agent,
    build_story_agent,
    build_issue_agent,
    build_graph_agent,
)

from google_adk.utils_adk import load_config
from google_adk.tools.ArangoUpsertTool import arango_upsert
from google_adk.tools.custom_tools import jira_get_epic_issues


# === Chunking Inputs ===


def epic_to_story_inputs(state):
    epics = state.get("epics_raw", {}).get("epics", [])
    for epic in epics:
        yield types.Content(
            role="user", parts=[types.Part(text=f"Get all stories for epic:\n{epic}")]
        )


def story_to_issue_inputs(state):
    stories = state.get("stories_raw", {}).get("stories", [])
    for story in stories:
        yield types.Content(
            role="user",
            parts=[types.Part(text=f"Get detailed issue for story:\n{story}")],
        )


def per_epic_graph_update_inputs(state):
    epics = state.get("epics_raw", {}).get("epics", [])
    for epic in epics:
        yield types.Content(
            role="user", parts=[types.Part(text=f"Update graph with epic:\n{epic}")]
        )


def per_story_graph_update_inputs(state):
    stories = state.get("stories_raw", {}).get("stories", [])
    for story in stories:
        yield types.Content(
            role="user", parts=[types.Part(text=f"Update graph with story:\n{story}")]
        )


def per_issue_graph_update_inputs(state):
    issues = state.get("issues_raw", {}).get("issues", [])
    for issue in issues:
        yield types.Content(
            role="user", parts=[types.Part(text=f"Update graph with issue:\n{issue}")]
        )


# === Pipeline Factory ===


def build_pipeline(jira_tools):
    """
    Constructs the Jira-to-Graph multi-agent pipeline using sequential and parallel execution.

    Args:
        jira_tools (List[BaseTool]): Tools loaded from the Jira MCP server.

    Returns:
        SequentialAgent: The fully constructed top-level pipeline.
    """
    models = load_config("runtime")["models"]["google"]
    return SequentialAgent(
        name="JiraGraphPipeline",
        sub_agents=[
            # 1a. Fetch epics
            build_epic_agent(model=models["epic"], tools=jira_tools),
            # 1b. Parallel graph updates per epic
            ParallelAgent.from_iterable(
                name="ParallelEpicGraphUpdate",
                agent_factory=lambda: build_graph_agent(
                    model=models["graph"],
                    prompt="epic_graph_prompt",
                    tools=[FunctionTool(arango_upsert)],
                ),
                inputs_provider=per_epic_graph_update_inputs,
            ),
            # 2a. Parallel story agents (uses custom FunctionTool)
            ParallelAgent.from_iterable(
                name="ParallelStoryAgents",
                agent_factory=lambda: build_story_agent(
                    model=models["story"], tools=[FunctionTool(jira_get_epic_issues)]
                ),
                inputs_provider=epic_to_story_inputs,
            ),
            # 2b. Parallel graph updates per story
            ParallelAgent.from_iterable(
                name="ParallelStoryGraphUpdate",
                agent_factory=lambda: build_graph_agent(
                    model=models["graph"],
                    prompt="story_graph_prompt",
                    tools=[FunctionTool(arango_upsert)],
                ),
                inputs_provider=per_story_graph_update_inputs,
            ),
            # 3a. Parallel issue agents (uses Jira MCP tools)
            ParallelAgent.from_iterable(
                name="ParallelIssuesAgents",
                agent_factory=lambda: build_issue_agent(
                    model=models["graph"], tools=jira_tools
                ),
                inputs_provider=story_to_issue_inputs,
            ),
            # 3b. Parallel graph updates per issue
            ParallelAgent.from_iterable(
                name="ParallelIssueGraphUpdate",
                agent_factory=lambda: build_graph_agent(
                    model=models["graph"],
                    prompt="issue_graph_prompt",
                    tools=[FunctionTool(arango_upsert)],
                ),
                inputs_provider=per_issue_graph_update_inputs,
            ),
        ],
    )
