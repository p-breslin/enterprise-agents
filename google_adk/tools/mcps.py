import os
from dotenv import load_dotenv
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioServerParameters,
)

load_dotenv()


async def jira_mcp_tools():
    """
    Connects to the mcp-atlassian MCP server and returns only selected tools.
    Creates an agent equipped with tools from the MCP Server.

    Note:
      MCP requires maintaining a connection to the local MCP Server. exit_stack manages the cleanup of this connection.
    """

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
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_TOKEN = os.getenv("JIRA_TOKEN")

    print("Connecting to Atlassian MCP server...")
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
    filtered_tools = [tool for tool in tools if tool.name in ALLOWED_TOOLS]
    # print(f"Available Jira tools: {[tool.name for tool in filtered_tools]}")
    return filtered_tools, exit_stack


async def arango_mcp_tools():
    """
    Connects to the ArangoDB MCP server and returns only selected tools.
    Used to construct agents that write to the knowledge graph.

    Note:
      MCP requires maintaining a connection to the local MCP Server. exit_stack manages the cleanup of this connection.
    """
    env = {
        "ARANGO_URL": os.getenv("ARANGO_HOST"),
        "ARANGO_DB": os.getenv("ARANGO_DB_JIRA"),
        "ARANGO_USERNAME": os.getenv("ARANGO_USERNAME"),
        "ARANGO_PASSWORD": os.getenv("ARANGO_PASSWORD"),
    }

    print("Connecting to ArangoDB MCP server...")
    tools, exit_stack = await MCPToolset.from_server(
        connection_params=StdioServerParameters(
            command="node",
            args=[
                "/Users/peter/ExperienceFlow/enterprise-agents/mcps/mcp-server-arangodb/build/index.js"
            ],
            env=env,
        )
    )
    print(f"Available Arango tools: {[tool.name for tool in tools]}")
    return tools, exit_stack
