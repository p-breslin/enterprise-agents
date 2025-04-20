import yaml
from pathlib import Path
from dotenv import load_dotenv

from agno.agent import Agent
from agno.tools.jira import JiraTools
from agno.models.google import Gemini

load_dotenv()


def load_prompts(prompt_key: str) -> str:
    path = Path(__file__).parent / "prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt_key]


def create_agent() -> Agent:
    """
    Agent created:
        JiraFetcherAgent

    Purpose:
        Fetches Jira issues updated in a given timeframe, filtered to type Bug or Story, returns structured ticket data (prompts.yaml for specifics).

    Tools:
        JiraTools for querying Jira via JQL.
    """
    prompts = load_prompts("jira_fetcher")

    return Agent(
        name="JiraFetcherAgent",
        model=Gemini(id="gemini-2.0-flash-exp"),
        tools=[JiraTools()],
        description=prompts["description"],
        instructions=prompts["instructions"],
        structured_outputs=True,
        show_tool_calls=True,
        markdown=False,
    )
