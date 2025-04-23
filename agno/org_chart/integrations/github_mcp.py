import os
import logging
from dotenv import load_dotenv
from utils_agno import load_config

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
)
log = logging.getLogger(__name__)


def get_github_mcp_config():
    """
    Returns the command string and environment dict for the GitHub MCP.
    """
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise ValueError("CRITICAL: GITHUB_PERSONAL_ACCESS_TOKEN not set.")

    # Load docker image from configuration
    cfg = load_config("runtime")["MCP_SERVERS"]
    docker_image = cfg["github"]

    # Set environment variables
    docker_command_base = "docker run -i --rm"
    docker_env_vars = ["-e GITHUB_PERSONAL_ACCESS_TOKEN"]

    # --- Optional: add toolset configuration here ---
    # toolsets = os.getenv("GITHUB_MCP_TOOLSETS") # e.g., "repos, issues"
    # if toolsets:
    #    docker_env_vars.append(f'-e GITHUB_TOOLSETS="{toolsets}"')

    mcp_command_string = (
        f"{docker_command_base} {' '.join(docker_env_vars)} {docker_image}"
    )

    process_env = {
        **os.environ,
        "GITHUB_PERSONAL_ACCESS_TOKEN": token,
    }

    log.info(f"MCP Config: Command='{mcp_command_string}'")
    return mcp_command_string, process_env
