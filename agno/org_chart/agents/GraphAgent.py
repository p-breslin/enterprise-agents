from agno.agent import Agent
from utils_agno import load_prompt


def build_graph_agent(model, tools, input_state_key: str, prompt_key: str):
    """
    Constructs the GraphAgent using Agno Agent.
     - Reads data from workflow session_state based on input_state_key.
     - Uses the specified prompt_key.
     - Returns an Agno Agent instance ready for execution.
    """
    prompt_template = load_prompt(prompt_key)
    instruction_text = prompt_template.replace("{state_key_name}", input_state_key)

    return Agent(
        model=model,
        name=f"GraphAgent_{prompt_key}",
        description=f"Reads data from state key '{input_state_key}' and updates an ArangoDB knowledge graph using available tools, following instructions from '{prompt_key}'.",
        instructions=[instruction_text],
        tools=tools,
        add_state_in_messages=True,
        response_model=None,  # Not required to return response
        markdown=False,  # No specific formatting needed for final output
    )
