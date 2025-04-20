from agno.agent import Agent
from schemas import StoryList
from utils_agno import load_prompt


def build_story_agent(model, tools, input_state_key: str):
    """
    Constructs the StoryAgent using Agno.
     - Reads epic data from workflow session_state.
     - Returns an Agno Agent instance ready for execution.
    """
    prompt_template = load_prompt("story_prompt")
    instruction_text = prompt_template.replace("{state_key_name}", input_state_key)

    return Agent(
        model=model,
        name="StoryAgent",
        description=f"Reads epic data from state key '{input_state_key}' and retrieves stories/tasks under each epic using available tools.",
        instructions=[instruction_text],
        tools=tools,
        add_state_in_messages=True,  # Enable agent access to session_state
        response_model=StoryList,  # Expecting structured output
        markdown=False,  # Output should be JSON
    )
