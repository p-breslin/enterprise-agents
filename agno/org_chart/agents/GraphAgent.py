from typing import Dict, List, Any
from .BaseAgent import _build_base_agent


def build_graph_agent(
    model: str,
    tools: List[Any],
    initial_state: Dict[str, Any],
    prompt: str,
    debug=False,
):
    """
    Constructs the GraphAgent using the base agent.
     - Reads data from workflow session_state based on initial_state.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name=f"GraphAgent_{prompt}",
        description="Reads data provided and updates an ArangoDB knowledge graph using available tools.",
        prompt_key=prompt,
        initial_state=initial_state,
        response_model=None,  # Not required to return response
        markdown=False,  # No specific formatting needed for final output
        debug=debug,
    )
