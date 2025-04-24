import os
import sys
import asyncio
from textwrap import dedent
from dotenv import load_dotenv

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from agno.models.openai import OpenAIChat

load_dotenv()


async def run_github_agent(message: str) -> None:
    """Runs an Agno agent equipped with GitHub MCP tools using Docker."""

    github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not github_token:
        print("Error: GITHUB_PERSONAL_ACCESS_TOKEN env variable not set.")
        sys.exit(1)

    # Base Docker command (-i for interactive, --rm to cleanup)
    docker_command_base = "docker run -i --rm"

    # Environment variables for the Docker container
    docker_env_vars = [
        "-e GITHUB_PERSONAL_ACCESS_TOKEN",
    ]

    # Can also add specific GITHUB_TOOLSETS in the env vars e.g.:
    # Enabling only repos and issues tools:  "-e GITHUB_TOOLSETS=repos,issues",
    # Enabling Dynamic Toolsets:  "-e GITHUB_DYNAMIC_TOOLSETS=1",

    # Docker image - Using the name from my personal Docker Desktop
    docker_image = "mcp/github-mcp-server:latest"

    # Combine into the full command string for MCPTools
    mcp_command_string = (
        f"{docker_command_base} {' '.join(docker_env_vars)} {docker_image}"
    )

    print(f"Attempting to start MCP server with command: {mcp_command_string}")
    print(f"Using Docker Image: {docker_image}")

    # Environment dictionary for the MCPTools process runner
    # This ensures the token is available when docker run executes
    process_env = {
        **os.environ,
        "GITHUB_PERSONAL_ACCESS_TOKEN": github_token,
        # Add other vars like GITHUB_TOOLSETS
    }

    try:
        # Use MCPTools as an async context manager to execute mcp_command_string
        async with MCPTools(mcp_command_string, env=process_env) as mcp_tools:
            print("GitHub MCP Server connected successfully via Docker.")

            # Create the Agno Agent
            agent = Agent(
                model=OpenAIChat(id="gpt-4.1-nano"),
                tools=[mcp_tools],
                instructions=dedent("""\
                    You are a helpful GitHub assistant.
                    Use the available tools to interact with GitHub repositories, issues, pull requests, etc.
                    Be precise in your actions. Ask for clarification if needed (e.g., repository owner/name).
                """),
                markdown=True,
                show_tool_calls=True,
            )

            print(f"\n--- Running Agent with message: '{message}' ---")
            await agent.aprint_response(message, stream=True)
            print("--- Agent run finished ---")

    except Exception as e:
        print("\n--- An error occurred ---")
        print(f"Error details: {e}")


# Example
if __name__ == "__main__":
    user_message = "Give me a brief summary of the latest activity in the 'p-breslin/enterprise-agents' repository. Include the message of the very last commit."

    asyncio.run(run_github_agent(user_message))
