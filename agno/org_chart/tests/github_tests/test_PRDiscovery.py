import logging
import asyncio
import pathlib
import datetime
from datetime import timedelta
from dotenv import load_dotenv
from models.schemas import PRDiscovery
from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
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
MODEL_ID = CFG["MODELS"][PROVIDER]["pr"]
MODEL = resolve_model(PROVIDER, MODEL_ID)
TEST_SESSION_ID = "test_session_PRAgent"

# Define Input (epics data from EpicAgent)
INPUT_DIR = pathlib.Path(__file__).parent / "../test_data"
INPUT_FILE = INPUT_DIR / "test_repo_data.json"
INPUT_STATE_KEY = "input_repo_data"

SAVENAME = f"test_PRDAgent_{MODEL_ID}.json"
OUTPUT_DIR = pathlib.Path(__file__).parent / "../test_output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / f"PRD_output_{MODEL_ID}.json"

# Docker command for MCP tools
MCP_CMD, MCP_ENV = get_github_mcp_config()

# Cutoff date
cutoff_date = (datetime.date.today() - timedelta(hours=25)).strftime("%Y-%m-%d")

# ----------------------------------------------------------


async def run_pr_agent_test():
    log.info("Starting PRAgent test.")

    # Load the input repo data and add cutoff_date
    initial_state = inject_state(INPUT_FILE, INPUT_STATE_KEY)
    initial_state["cutoff_date"] = cutoff_date

    async with MCPTools(MCP_CMD, env=MCP_ENV) as mcp_tools:
        agent = build_pr_agent(
            model=MODEL,
            tools=[mcp_tools],
            initial_state=initial_state,
            prompt="pr_discovery_prompt",
            debug=DEBUG,
        )

        # Run agent
        log.info("Running PRAgent...")
        trigger_message = "Fetch pull requests for the given repo"
        resp: RunResponse = await agent.arun(
            trigger_message, session_id=TEST_SESSION_ID
        )
        assert resp.content, "PRAgent returned empty content"
        pprint_run_response(resp)

        # Validate and save output
        outfile = OUTPUT_DIR / SAVENAME
        json_obj = parse_json(resp.content)
        validate_output(outfile, json_obj, PRDiscovery)


if __name__ == "__main__":
    asyncio.run(run_pr_agent_test())
