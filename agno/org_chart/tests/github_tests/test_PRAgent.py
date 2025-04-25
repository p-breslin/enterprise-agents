import logging
import asyncio
import pathlib
from dotenv import load_dotenv
from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
from models.schemas import PullRequestList
from agno.utils.pprint import pprint_run_response
from integrations.github_mcp import get_github_mcp_config

from agents import build_pr_agent
from utils.helpers import (
    load_config,
    resolve_model,
    inject_state,
    validate_output,
    parse_json,
)

load_dotenv()
log = logging.getLogger(__name__)


# Runtime setup --------------------------------------------

DEBUG = True
PROVIDER = "google"
CFG = load_config("runtime")
ORG = CFG["GITHUB"]["org"]
MODEL_ID = CFG["MODELS"][PROVIDER]["repo"]
MODEL = resolve_model(PROVIDER, MODEL_ID)
TEST_SESSION_ID = "test_session_PRAgent"

# Define Input (epics data from EpicAgent)
INPUT_DIR = pathlib.Path(__file__).parent / "../test_data"
INPUT_FILE = INPUT_DIR / "test_repo_data.json"
INPUT_STATE_KEY = "repo_data_input"

SAVENAME = f"test_PRAgent_{MODEL_ID}.json"
OUTPUT_DIR = pathlib.Path(__file__).parent / "../test_output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / f"PR_output_{MODEL_ID}.json"

# Docker command for MCP tools
MCP_CMD, MCP_ENV = get_github_mcp_config()

# ----------------------------------------------------------


async def run_pr_agent_test():
    log.info("Starting PRAgent test.")

    # Load the input repo data
    initial_state = inject_state(INPUT_FILE, INPUT_STATE_KEY)

    async with MCPTools(MCP_CMD, env=MCP_ENV) as mcp_tools:
        agent = build_pr_agent(
            model=MODEL,
            tools=[mcp_tools],
            initial_state=initial_state,
            debug=DEBUG,
        )

        # Run agent
        log.info("Running PRAgent...")
        trigger_message = "Fetch pull requests for supplied repos"
        resp: RunResponse = await agent.arun(
            trigger_message, session_id=TEST_SESSION_ID
        )
        assert resp.content, "PRAgent returned empty content"
        pprint_run_response(resp)

        # Validate and save output
        outfile = OUTPUT_DIR / SAVENAME
        json_obj = parse_json(resp.content)
        validate_output(outfile, json_obj, PullRequestList)


if __name__ == "__main__":
    asyncio.run(run_pr_agent_test())
