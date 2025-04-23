from models.schemas import EpicList
from .BaseAgent import _build_base_agent


def build_epic_agent(model, tools, prompt="epic_prompt", debug=False):
    """
    Constructs the EpicAgent using the base builder.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name="EpicAgent",
        description="Fetches all Jira epics using the jira_search tool and formats them as JSON.",
        prompt_key=prompt,
        response_model=EpicList,  # Expecting structured output
        markdown=False,  # Output must be pure JSON
        debug=debug,
    )
