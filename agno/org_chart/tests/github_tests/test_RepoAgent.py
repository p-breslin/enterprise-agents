import logging
import asyncio
import pathlib
from dotenv import load_dotenv
from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
from agno.utils.pprint import pprint_run_response

from agents import build_repo_agent
from models.schemas import RepoList
from utils.logging_setup import setup_logging
from integrations.github_mcp import get_github_mcp_config
from utils.helpers import load_config, resolve_model, validate_output

load_dotenv()
setup_logging()
log = logging.getLogger(__name__)

# Runtime setup
DEBUG = False
CFG = load_config("runtime")
ORG = CFG["GITHUB"]["org"]
MODEL = resolve_model("openai", CFG["MODELS"]["openai"]["repo"])

# Paths
SAVENAME = f"test_RepoAgent_{MODEL}.json"
TEST_DIR = pathlib.Path(__file__).parent
OUTPUT_DIR = TEST_DIR / "../test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Docker command for MCP tools
MCP_CMD, MCP_ENV = get_github_mcp_config()


async def run_repo_agent_test():
    async with MCPTools(MCP_CMD, env=MCP_ENV) as mcp_tools:
        for tool in mcp_tools.tools:
            if "parameters" in tool.schema:
                tool.schema["parameters"].setdefault("additionalProperties", False)

        agent = build_repo_agent(
            model=MODEL,
            tools=[mcp_tools],
            debug=DEBUG,
        )
        trigger = f"Scan GitHub org {ORG} for active repos"
        resp: RunResponse = await agent.arun(trigger, session_id="repo_agent_test")

        assert resp.content, "RepoAgent returned empty content"
        pprint_run_response(resp, markdown=True)

        # Validate and save output
        outfile = OUTPUT_DIR / SAVENAME
        validate_output(outfile, resp.content.repos, RepoList)


if __name__ == "__main__":
    asyncio.run(run_repo_agent_test())
