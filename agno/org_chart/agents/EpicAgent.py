from agno.agent import Agent
from schemas import EpicList
from utils_agno import load_prompt


def build_epic_agent(model, tools, prompt="epic_prompt"):
    """
    Constructs the EpicAgent using Agno.
     - Returns an Agno Agent instance ready for execution.
    """
    prompt_text = load_prompt(prompt)

    return Agent(
        model=model,
        name="EpicAgent",
        description="Fetches all Jira epics using the jira_search tool and formats them as JSON.",
        instructions=[prompt_text],
        tools=tools,
        response_model=EpicList,  # Expecting structured output
        markdown=False,  # Output must be pure JSON
    )
