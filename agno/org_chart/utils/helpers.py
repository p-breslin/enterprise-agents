import os
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv

from agno.models.google import Gemini
from agno.models.openai import OpenAIChat


load_dotenv()
log = logging.getLogger(__name__)


def load_prompt(prompt: str) -> str:
    path = Path(__file__).parent / "configs/prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt]


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
        log.info(f"Successfully saved YAML to {os.path.basename(filepath)}")
        return True
    except Exception as e:
        log.error(f"An error occurred saving: {e}", exc_info=True)
        return False


def resolve_model(provider: str, model_id: str):
    if provider == "google":
        return Gemini(id=model_id)
    if provider == "openai":
        return OpenAIChat(id=model_id, temperature=0)
