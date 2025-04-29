from typing import List, Any, Dict, Optional
from .BaseAgent import _build_base_agent


def build_branch_agent(
    model: str,
    tools: List[Any],
    initial_state: Optional[Dict[str, Any]] = None,
    prompt: str = "branch_prompt",
    debug: bool = False,
):
    """
    Constructs the BranchAgent using the base agent.
     - Dynamically discovers relevant branches within the given repositories.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name="BranchAgent",
        description="Discovers branches for the given GitHub repository.",
        prompt_key=prompt,
        initial_state=initial_state,
        response_model=None,
        markdown=False,
        debug=debug,
    )
