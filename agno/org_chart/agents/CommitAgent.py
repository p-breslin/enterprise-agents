from typing import List, Any, Dict, Optional
from .BaseAgent import _build_base_agent


def build_commit_agent(
    model: str,
    tools: List[Any],
    initial_state: Optional[Dict[str, Any]] = None,  # expects PR context
    prompt: str = "pr_commit_prompt",
    debug: bool = False,
):
    """
    Constructs the CommitAgent using the base agent.
     - Lists commits and pull commit-level stats / checks for each PR.
     - Emits additions, deletions, author_login, sha, status contexts, etc.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name="CommitAgent",
        description="Gathers commit objects and status-check results for a PR.",
        prompt_key=prompt,
        initial_state=initial_state,
        response_model=None,
        markdown=False,
        debug=debug,
    )
