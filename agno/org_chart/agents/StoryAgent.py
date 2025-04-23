from typing import Dict, List, Any
from models.schemas import StoryList
from .BaseAgent import _build_base_agent


def build_story_agent(
    model: str,
    tools: List[Any],
    initial_state: Dict[str, Any],
    prompt="story_prompt",
    debug=False,
):
    """
    Constructs the StoryAgent using the base builder.
     - Reads Epic data from workflow session_state.
    """
    return _build_base_agent(
        model=model,
        tools=tools,
        name="StoryAgent",
        description="Reads epic data provided and retrieves stories/tasks under each epic using available tools.",
        prompt_key=prompt,
        response_model=StoryList,  # Expecting structured output
        initial_state=initial_state,
        markdown=False,  # Output should be JSON
        debug=debug,
    )
