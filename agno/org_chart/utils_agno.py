import os
import yaml
import logging
from pathlib import Path
from atlassian import Jira
from typing import Optional
from dotenv import load_dotenv

from agno.models.google import Gemini
from agno.models.openai import OpenAIChat


load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def load_prompt(prompt_key: str) -> str:
    path = Path(__file__).parent / "prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt_key]


def load_config(folder):
    path = Path(__file__).parent / f"configs/{folder}.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def get_jira_client() -> Optional[Jira]:
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_TOKEN = os.getenv("JIRA_TOKEN")

    try:
        jira = Jira(
            url=JIRA_SERVER_URL, username=JIRA_USERNAME, password=JIRA_TOKEN, cloud=True
        )
        logger.info(f"Connected to Jira: {JIRA_SERVER_URL}")
        return jira
    except Exception as e:
        logger.error(f"Failed to connect to Jira: {e}")
        return None


def resolve_model(provider: str, model_id: str):
    if provider == "google":
        return Gemini(id=model_id)
    if provider == "openai":
        return OpenAIChat(id=model_id)
