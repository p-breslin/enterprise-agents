import os
import logging
from dotenv import load_dotenv
from utils.helpers import load_config

load_dotenv()
log = logging.getLogger(__name__)


def get_github_mcp_config(toolsets=True):
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
    docker_env_vars = ["-e GITHUB_PERSONAL_ACCESS_TOKEN"]
    process_env = {**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": token}

    # Toolset configuration
    if toolsets:
        tools = os.getenv("GITHUB_TOOLSETS")
        docker_env_vars.append("-e GITHUB_TOOLSETS")
        process_env["GITHUB_TOOLSETS"] = tools
        log.info(f"Toolset specified: {tools}")

    mcp_command_string = (
        f"docker run -i --rm {' '.join(docker_env_vars)} {docker_image}"
    )
    log.info(f"MCP Config: Command='{mcp_command_string}'")
    return mcp_command_string, process_env
