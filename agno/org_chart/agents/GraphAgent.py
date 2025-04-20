from agno.agent import Agent
from utils_agno import load_prompt


def build_graph_agent(model, tools, initial_state: str, prompt_key: str):
    """
    Constructs the GraphAgent using Agno Agent.
     - Reads data from workflow session_state based on initial_state.
     - Uses the specified prompt_key.
     - Returns an Agno Agent instance ready for execution.
    """
    instruction_text = load_prompt(prompt_key)
    return Agent(
        model=model,
        name=f"GraphAgent_{prompt_key}",
        description="Reads data provided and updates an ArangoDB knowledge graph using available tools.",
        instructions=[instruction_text],
        tools=tools,
        session_state=initial_state,
        add_state_in_messages=True,
        response_model=None,  # Not required to return response
        markdown=False,  # No specific formatting needed for final output
    )
