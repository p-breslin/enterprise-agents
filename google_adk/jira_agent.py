import os
import yaml
import json
import asyncio
from typing import List
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioServerParameters,
)


class JiraIssues(BaseModel):
    issue_id: str
    summary: str
    assignee: str
    project: str
    last_updated: str


class JiraIssuesList(BaseModel):
    issues: List[JiraIssues]


def load_prompt(prompt_key: str) -> str:
    path = Path(__file__).parent / "prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt_key]


# Only want to expose read-only Jira tools
ALLOWED_TOOLS = {
    "jira_get_issue",
    "jira_search",
    "jira_get_project_issues",
    "jira_get_epic_issues",
    "jira_get_transitions",
    "jira_get_agile_boards",
    "jira_get_board_issues",
    "jira_get_sprints_from_board",
    "jira_get_sprint_issues",
}

load_dotenv()
JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")


# Import tools from the MCP server
async def get_tools_async():
    """
    Connects to the mcp-atlassian MCP server and returns only selected tools.

    Note:
      MCP requires maintaining a connection to the local MCP Server. exit_stack manages the cleanup of this connection.
    """
    print("Connecting to MCP Atlassian server...")
    tools, exit_stack = await MCPToolset.from_server(
        connection_params=StdioServerParameters(
            command="mcp-atlassian",
            args=[
                f"--jira-url={JIRA_SERVER_URL}",
                f"--jira-username={JIRA_USERNAME}",
                f"--jira-token={JIRA_TOKEN}",
            ],
        )
    )
    print("MCP toolset created successfully.")

    # Filter tools to include only the allowed Jira tools
    filtered_tools = [tool for tool in tools if tool.name in ALLOWED_TOOLS]
    print(f"Filtered tools: {[tool.name for tool in filtered_tools]}")
    return filtered_tools, exit_stack


# Agent definition
async def get_tool_agent():
    """
    Creates an agent equipped with tools from the MCP Server.
    """
    tools, exit_stack = await get_tools_async()
    print(f"Fetched {len(tools)} tools from the MCP server.")

    tool_agent = LlmAgent(
        model="gemini-2.0-flash",
        name="jira_tools_agent",
        description="Fetches Jira issue data using tools.",
        instruction=load_prompt("tool_prompt"),
        tools=tools,
    )
    return tool_agent, exit_stack


async def get_structure_agent():
    """
    Creates an agent tasked with adding JSON structure to the the tool agent's response (invoking output schema removes tool use with Google ADK).
    """
    structure_agent = LlmAgent(
        model="gemini-2.0-flash",
        name="jira_structure_agent",
        description="Formats Jira issue summaries into structured JSON.",
        instruction=load_prompt("structure_prompt"),
        output_schema=JiraIssuesList,
        output_key="issues",
        disallow_transfer_to_peers=True,
        disallow_transfer_to_parent=True,
    )
    return structure_agent


# Main execution logic
async def async_main():
    session_service = InMemorySessionService()
    artifacts_service = InMemoryArtifactService()

    session = session_service.create_session(
        state={}, app_name="mcp_jira_app", user_id="user_jira"
    )

    query = "List issues updated in the last 30 days and who is working on them"
    print(f"User Query: '{query}'")
    content = types.Content(role="user", parts=[types.Part(text=query)])

    tool_agent, exit_stack = await get_tool_agent()
    structure_agent = await get_structure_agent()

    # First agent uses MCP tool
    tool_runner = Runner(
        app_name="mcp_jira_app",
        agent=tool_agent,
        artifact_service=artifacts_service,
        session_service=session_service,
    )

    print("Running tool agent...")
    tool_output = None
    async for event in tool_runner.run_async(
        session_id=session.id, user_id=session.user_id, new_message=content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            tool_output = event.content.parts[0].text

    print("Tool agent output:\n", tool_output)

    # Second agent adds structure to the response
    structure_runner = Runner(
        app_name="mcp_jira_app",
        agent=structure_agent,
        artifact_service=artifacts_service,
        session_service=session_service,
    )

    structure_content = types.Content(role="user", parts=[types.Part(text=tool_output)])
    print("Running structure agent...")
    async for event in structure_runner.run_async(
        session_id=session.id, user_id=session.user_id, new_message=structure_content
    ):
        if event.is_final_response() and event.content and event.content.parts:
            structure_output = event.content.parts[0].text
            print("Structured output (raw JSON):\n", structure_output)

            try:
                parsed = json.loads(structure_output)
                print("Structured output:")
                print(json.dumps(parsed.get("issues", []), indent=2))
            except json.JSONDecodeError:
                print("Could not parse structured output as JSON.")

    # Crucial Cleanup: Ensure the MCP server process connection is closed.
    print("Closing MCP server connection...")
    await exit_stack.aclose()
    print("Cleanup complete.")


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except Exception as e:
        print(f"An error occurred: {e}")
