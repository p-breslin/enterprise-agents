import json
import logging
import asyncio
from dotenv import load_dotenv
from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
from agno.utils.pprint import pprint_run_response

from agents import build_pr_agent
from utils.helpers import load_config, resolve_model
from integrations.github_mcp import get_github_mcp_config

load_dotenv()
log = logging.getLogger(__name__)

# Runtime setup
DEBUG = False
CFG = load_config("runtime")
ORG = CFG["GITHUB"]["org"]
MODEL = resolve_model("openai", CFG["MODELS"]["openai"]["repo"])

# Docker command for MCP tools
MCP_CMD, MCP_ENV = get_github_mcp_config()

# prepare minimal repo list in session_state
repo_stub = {
    "owner": "xpander-ai",
    "repo": "xpander-sdk",
    "default_branch": "main",
    "visibility": "public",
    "updated_at": "2025-04-24T18:16:55Z",
}
state_key = "repos_data_input"  # align with future runtime.yaml update
initial_state = {state_key: json.dumps({"repos": [repo_stub]})}

MCP_CMD, MCP_ENV = get_github_mcp_config()


async def run_pr_agent_test():
    async with MCPTools(MCP_CMD, env=MCP_ENV) as mcp_tools:
        agent = build_pr_agent(
            model=MODEL,
            tools=[mcp_tools],
            initial_state=initial_state,
            debug=DEBUG,
        )
        response: RunResponse = await agent.arun(
            "Fetch pull requests for supplied repos",
            session_id="pr_agent_test",
        )
        assert response.content, "PRAgent returned empty content"
        pprint_run_response(response)


if __name__ == "__main__":
    asyncio.run(run_pr_agent_test())
