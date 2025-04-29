import os
import json
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv

from agno.models.google import Gemini
from agno.models.openai import OpenAIChat
from agno.models.openrouter import OpenRouter


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
        return Gemini(id=model_id, temperature=0)
    if provider == "openai":
        return OpenAIChat(id=model_id, temperature=0)
    if provider == "openrouter":
        return OpenRouter(
            id=model_id, api_key=os.getenv("OPENROUTER_API_KEY"), temperature=0
        )


def validate_output(ouutput_path, output_content, schema):
    """
    Validates an agent's structured response to the predefined schema. Response then saved to a JSON file (in test_outputs/ by default).
    """
    try:
        # Ensure JSON object is a Pydantic model instance
        if not isinstance(output_content, schema):
            output_content = schema(**output_content)

        with open(ouutput_path, "w") as f:
            json.dump(output_content.model_dump(), f, indent=4)
            log.info(f"Saved structured output to {ouutput_path}")
    except IOError as e:
        log.error(f"Failed to write output file {ouutput_path}: {e}")

    # Handle case if content isn't a Pydantic model
    except AttributeError:
        log.warning("Output content does not have model_dump method.")

        # Fallback: try saving raw content
        try:
            with open(ouutput_path.with_suffix(".raw.json"), "w") as f:
                json.dump(output_content, f, indent=4)
        except Exception:
            log.error("Could not save raw output content.")


def parse_json(json_string: str):
    """Tries to parse a string as JSON."""
    try:
        # Strip whitespace
        text = json_string.strip()

        # Remove ticks if necessary
        text = text.strip().strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def inject_state(input_file, state_key):
    """Injects data into the session state for an Agno agent."""
    state = {}
    try:
        with open(input_file, "r") as f:
            raw_input_data = json.load(f)
            state[state_key] = json.dumps(raw_input_data, indent=2)
            log.info(
                f"Loaded input data from {input_file} into state key '{state_key}'."
            )
            return state
    except Exception as e:
        log.critical(f"Failed to load input file {input_file}: {e}")
        raise
