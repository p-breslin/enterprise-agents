from typing import List, Any, Dict, Optional
from .BaseAgent import _build_base_agent


def build_pr_agent(
    model: str,
    tools: List[Any],
    initial_state: Optional[Dict[str, Any]] = None,  # expects repo metadata
    prompt: str = "pr_prompt",
    debug: bool = False,
):
    """
    Constructs the PRAgent using the base builder.
     - Lists / fetches PRs updated for each repo in session_state.
     - Parses key fields.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name="PRAgent",
        description="Retrieves pull-request metadata from GitHub via MCP.",
        prompt_key=prompt,
        initial_state=initial_state,
        response_model=None,
        markdown=False,
        debug=debug,
    )
