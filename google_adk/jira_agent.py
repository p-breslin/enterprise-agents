import os
import json
import asyncio
from dotenv import load_dotenv

from schemas import JiraIssuesList
from utils import load_prompt, log_event_details, save_json

from google.genai import types
from google.adk.runners import Runner
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent

from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioServerParameters,
)


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
async def get_tool_agent():
    """
    Connects to the mcp-atlassian MCP server and returns only selected tools.
    Creates an agent equipped with tools from the MCP Server.

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

    # Filter tools to include only the allowed Jira tools
    filtered_tools = [tool for tool in tools if tool.name in ALLOWED_TOOLS]
    print(f"Filtered tools: {[tool.name for tool in filtered_tools]}")

    agent = LlmAgent(
        model="gemini-2.0-flash-lite",
        name="jira_tools_agent",
        description="Fetches Jira issue data using tools.",
        instruction=load_prompt("tool_prompt"),
        tools=filtered_tools,
        output_key="raw_issues",
    )
    return agent, exit_stack


async def get_structure_agent():
    """
    Creates an agent tasked with adding JSON structure to the the tool agent's response (invoking output schema removes tool use with Google ADK).
    """
    return LlmAgent(
        model="gemini-2.0-flash-exp",
        name="jira_structure_agent",
        description="Formats Jira issue summaries into structured JSON.",
        instruction=load_prompt("structure_prompt"),
        output_schema=JiraIssuesList,
        output_key="structured_issues",
        disallow_transfer_to_peers=True,
        disallow_transfer_to_parent=True,
    )


# Main execution logic
async def async_main():
    session_service = InMemorySessionService()
    artifacts_service = InMemoryArtifactService()
    app_name = "mcp_jira_app"
    session_id = "jira_seq_session"
    user_id = "user_jira"

    session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    tool_agent, exit_stack = await get_tool_agent()
    structure_agent = await get_structure_agent()
    sequential_agent = SequentialAgent(
        name="jira_pipeline_agent", sub_agents=[tool_agent, structure_agent]
    )

    runner = Runner(
        agent=sequential_agent,
        app_name=app_name,
        session_service=session_service,
        artifact_service=artifacts_service,
    )

    query = "Get all Jira issues updated in the last 7 days."
    print(f"User Query: '{query}'")
    content = types.Content(role="user", parts=[types.Part(text=query)])

    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=content
    ):
        log_event_details(event)
        if event.is_final_response() and event.content and event.content.parts:
            if event.author == "jira_structure_agent":
                try:
                    parsed = json.loads(event.content.parts[0].text)
                    save_json(parsed)
                except json.JSONDecodeError:
                    print("Could not parse structured output as JSON.")

    # Ensure the MCP server process connection is closed
    print("Closing MCP server connection...")
    await exit_stack.aclose()
    print("Cleanup complete.")


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except Exception as e:
        print(f"An error occurred: {e}")
