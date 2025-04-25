import json
import logging
import asyncio
from dotenv import load_dotenv
from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
from agno.utils.pprint import pprint_run_response

from agents import build_commit_agent
from utils.helpers import load_config, resolve_model
from integrations.github_mcp import get_github_mcp_config

load_dotenv()
log = logging.getLogger(__name__)

# Runtime setup
DEBUG = True
CFG = load_config("runtime")
ORG = CFG["GITHUB"]["org"]
MODEL = resolve_model("openai", CFG["MODELS"]["openai"]["repo"])

# Docker command for MCP tools
MCP_CMD, MCP_ENV = get_github_mcp_config()

PR_NUMBER = 342
pr_stub = {
    "owner": "xpander-ai",
    "repo": "xpander-sdk",
    "pr_number": f"{PR_NUMBER}",
    "head_sha": "98e01ad7c7c91e4388b297065b829dbf37dd99cc",
}
state_key = "prs_data_input"
initial_state = {state_key: json.dumps({"pull_requests": [pr_stub]})}

MCP_CMD, MCP_ENV = get_github_mcp_config()


async def run_commit_agent_test():
    async with MCPTools(MCP_CMD, env=MCP_ENV) as mcp_tools:
        agent = build_commit_agent(
            model=MODEL,
            tools=[mcp_tools],
            initial_state=initial_state,
            debug=DEBUG,
        )
        resp: RunResponse = await agent.arun(
            f"Collect commits for PR #{PR_NUMBER}",
            session_id="commit_agent_test",
        )
        assert resp.content, "CommitAgent returned empty content"
        pprint_run_response(resp, markdown=True)


if __name__ == "__main__":
    asyncio.run(run_commit_agent_test())
