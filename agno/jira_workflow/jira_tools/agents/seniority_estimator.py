import yaml
from pathlib import Path
from dotenv import load_dotenv

from agno.agent import Agent
from agno.models.google import Gemini

load_dotenv()


def load_prompts(prompt_key: str) -> str:
    path = Path(__file__).parent / "prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt_key]


def create_agent() -> Agent:
    """
    Agent created:
        SeniorityEstimatorAgent

    Purpose:
        Estimates each engineer’s seniority level (junior/mid/senior) based on their ticket activity and resolution speed (see prompt.yaml for classification rules).

    Tools:

    """
    prompts = load_prompts("seniority_estimator")
    return Agent(
        name=prompts.get("name", "SeniorityEstimatorAgent"),
        model=Gemini(id="gemini-2.0-flash-exp"),
        description=prompts["description"],
        instructions=prompts["instructions"],
        structured_outputs=True,
        show_tool_calls=True,
        markdown=False,
    )
