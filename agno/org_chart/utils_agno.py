import os
import yaml
import logging
from jira import JIRA
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from agno.models.google import Gemini
from agno.models.openai import OpenAIChat


load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# --- Module-level cache for JIRA client ---
_cached_jira_client: Optional[JIRA] = None


def load_prompt(prompt_key: str) -> str:
    path = Path(__file__).parent / "prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt_key]


def load_config(file):
    path = Path(__file__).parent / f"configs/{file}.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def save_yaml(filepath, data):
    """
    Saves data to a YAML file.
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=True)
        logger.info(f"Successfully saved YAML to {os.path.basename(filepath)}")
        return True
    except Exception as e:
        logger.error(f"An error occurred saving: {e}", exc_info=True)
        return False


def get_jira_client() -> Optional[JIRA]:
    """
    Returns a cached JIRA client instance (initializes it on first call).
    """
    global _cached_jira_client

    # Return cached client if already initialized
    if _cached_jira_client is not None:
        logger.debug("Returning cached JIRA client.")
        return _cached_jira_client

    # Initialize client if not cached
    logger.info("Initializing new JIRA client...")
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_TOKEN = os.getenv("JIRA_TOKEN")

    try:
        jira_options = {"server": JIRA_SERVER_URL}
        jira = JIRA(options=jira_options, basic_auth=(JIRA_USERNAME, JIRA_TOKEN))
        logger.info(f"Connected to JIRA: {JIRA_SERVER_URL}. Caching client.")
        _cached_jira_client = jira  # Store client to cache
        return _cached_jira_client
    except Exception as e:
        logger.error(f"Failed to connect to JIRA: {e}")
        _cached_jira_client = None
        return None


def reset_jira_client_cache():
    """
    Resets the cached JIRA client.
    """
    global _cached_jira_client
    logger.debug("Resetting cached JIRA client.")
    _cached_jira_client = None


def resolve_model(provider: str, model_id: str):
    if provider == "google":
        return Gemini(id=model_id)
    if provider == "openai":
        return OpenAIChat(id=model_id)
