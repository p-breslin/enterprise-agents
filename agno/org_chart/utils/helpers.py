import os
import json
import yaml
import logging
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Any, Union

from agno.models.google import Gemini
from agno.models.openai import OpenAIChat


load_dotenv()
log = logging.getLogger(__name__)


def load_prompt(prompt: str) -> str:
    path = Path(__file__).parent / "../configs/prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt]


def load_config(file):
    path = Path(__file__).parent / f"../configs/{file}.yaml"
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


def validate_output(ouutput_path, output_content, schema):
    """
    Validates an agent's structured response to the predefined schema. Response then saved to a JSON file (in test_outputs/ by default).
    """
    try:
        # Save the validated Pydantic model data
        with open(ouutput_path, "w") as f:
            json.dump(output_content.model_dump(), f, indent=4)
            log.info(f"Saved structured output to {ouutput_path}")
    except IOError as e:
        log.error(f"Failed to write output file {ouutput_path}: {e}")

    # Handle case if content isn't a Pydantic model
    except AttributeError:
        log.error("Output content does not have model_dump method.")

        # Fallback: try saving raw content if content exists
        if not isinstance(output_content, schema):
            try:
                with open(ouutput_path.with_suffix(".raw.json"), "w") as f:
                    json.dump(output_content, f, indent=4)
            except Exception:
                log.error("Could not save raw output content.")
