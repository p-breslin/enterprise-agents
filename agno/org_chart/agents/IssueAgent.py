from typing import Dict, List, Any
from models.schemas import IssueList
from .BaseAgent import _build_base_agent


def build_issue_agent(
    model: str,
    tools: List[Any],
    initial_state: Dict[str, Any],
    prompt="issue_prompt",
    debug=False,
):
    """
    Constructs the IssueAgent using the base builder.
     - Reads Story data from workflow session_state.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name="IssueAgent",
        description="Reads story data provided and fetches metadata from Jira issues using available tools.",
        prompt_key=prompt,
        response_model=IssueList,  # Expecting structured output
        initial_state=initial_state,
        markdown=False,  # Output should be JSON
        debug=debug,
    )
