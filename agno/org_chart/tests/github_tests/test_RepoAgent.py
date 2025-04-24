import logging
import asyncio
from dotenv import load_dotenv
from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
from agno.utils.pprint import pprint_run_response

from agents import build_repo_agent
from utils.helpers import load_config, resolve_model
from integrations.github_mcp import get_github_mcp_config

load_dotenv()
log = logging.getLogger(__name__)

# Runtime setup
CFG = load_config("runtime")
ORG = CFG["GITHUB"]["org"]
MODEL = resolve_model("openai", CFG["MODELS"]["openai"]["repo"])

# Docker command for MCP tools
MCP_CMD, MCP_ENV = get_github_mcp_config()


async def run_repo_agent_test():
    async with MCPTools(MCP_CMD, env=MCP_ENV) as mcp_tools:
        agent = build_repo_agent(
            model=MODEL,
            tools=[mcp_tools],
            debug=True,
        )
        trigger = f"Scan GitHub org {ORG} for active repos"
        response: RunResponse = await agent.arun(trigger, session_id="repo_agent_test")

        assert response.content, "RepoAgent returned empty content"
        pprint_run_response(response, markdown=True)


if __name__ == "__main__":
    asyncio.run(run_repo_agent_test())
