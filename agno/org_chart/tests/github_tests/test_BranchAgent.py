import logging
import asyncio
import pathlib
from dotenv import load_dotenv
from models.schemas import BranchList
from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
from agno.utils.pprint import pprint_run_response
from integrations.github_mcp import get_github_mcp_config

from agents import build_branch_agent
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
MODEL_ID = CFG["MODELS"][PROVIDER]["pr"]
MODEL = resolve_model(PROVIDER, MODEL_ID)
TEST_SESSION_ID = "test_session_BranchAgent"

# Define Input (epics data from EpicAgent)
INPUT_DIR = pathlib.Path(__file__).parent / "../test_data"
INPUT_FILE = INPUT_DIR / "test_repo_data.json"
INPUT_STATE_KEY = "input_repo_data"

SAVENAME = f"test_BranchAgent_{MODEL_ID}.json"
OUTPUT_DIR = pathlib.Path(__file__).parent / "../test_output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / f"branch_output_{MODEL_ID}.json"

# Docker command for MCP tools
MCP_CMD, MCP_ENV = get_github_mcp_config()

# ----------------------------------------------------------


async def run_branch_agent_test():
    log.info("Starting BranchAgent test.")

    # Load the input repo data and add cutoff_date
    initial_state = inject_state(INPUT_FILE, INPUT_STATE_KEY)

    async with MCPTools(MCP_CMD, env=MCP_ENV) as mcp_tools:
        agent = build_branch_agent(
            model=MODEL,
            tools=[mcp_tools],
            initial_state=initial_state,
            prompt="branch_prompt",
            debug=DEBUG,
        )

        # Run agent
        log.info("Running BranchAgent...")
        trigger_message = "Fetch branches for the given repository"
        resp: RunResponse = await agent.arun(
            trigger_message, session_id=TEST_SESSION_ID
        )
        assert resp.content, "BranchAgent returned empty content"
        pprint_run_response(resp)

        # Validate and save output
        outfile = OUTPUT_DIR / SAVENAME
        json_obj = parse_json(resp.content)
        validate_output(outfile, json_obj, BranchList)


if __name__ == "__main__":
    asyncio.run(run_branch_agent_test())
