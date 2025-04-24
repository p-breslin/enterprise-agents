from typing import List, Any, Dict, Optional
from .BaseAgent import _build_base_agent


def build_review_agent(
    model: str,
    tools: List[Any],
    initial_state: Optional[Dict[str, Any]] = None,  # expects PR context
    prompt: str = "review_prompt",
    debug: bool = False,
):
    """
    Constructs the ReviewAgent using the base agent.
     - Fetches reviews + review comments given a PR number.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name="ReviewAgent",
        description="Collects review decisions and comments for pull requests.",
        prompt_key=prompt,
        initial_state=initial_state,
        response_model=None,
        markdown=False,
        debug=debug,
    )
