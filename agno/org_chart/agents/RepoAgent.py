from typing import List, Any
from models.schemas import RepoList
from .BaseAgent import _build_base_agent


def build_repo_agent(
    model: str,
    tools: List[Any],
    prompt: str = "repo_prompt",
    debug: bool = False,
):
    """
    Constructs the RepoAgent using the base builder.
     - Enumerates repos the org owns or that match a given pattern.
     - Lists branches and basic repo metadata.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name="RepoAgent",
        description="Discovers GitHub repositories and branches using MCP repo-level tools.",
        prompt_key=prompt,
        response_model=None,  # mcp issues with openai when outputs structured..
        markdown=False,
        debug=debug,
    )
