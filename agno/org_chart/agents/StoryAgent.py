from agno.agent import Agent
from schemas import StoryList
from utils_agno import load_prompt


def build_story_agent(model, tools, initial_state: dict, prompt="story_prompt"):
    """
    Constructs the StoryAgent using Agno.
     - Reads epic data from workflow session_state.
     - Returns an Agno Agent instance ready for execution.
    """
    instruction_text = load_prompt(prompt)
    return Agent(
        model=model,
        name="StoryAgent",
        description="Reads epic data provided and retrieves stories/tasks under each epic using available tools.",
        instructions=[instruction_text],
        tools=tools,
        session_state=initial_state,
        add_state_in_messages=True,  # Enable agent access to session_state
        response_model=StoryList,  # Expecting structured output
        markdown=False,  # Output should be JSON
    )
