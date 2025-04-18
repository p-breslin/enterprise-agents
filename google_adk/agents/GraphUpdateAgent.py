from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_graph_agent(model, prompt, tools, input_key, output_key=None):
    """
    Constructs the GraphUpdateAgent with access to ArangoDB MCP tools.
    Returns an LlmAgent instance ready for execution.
    """
    prmt = load_prompt(prompt)
    instruction = prompt.replace("{state_key_name}", input_key)
    return LlmAgent(
        model=model,
        name="GraphUpdateAgent",
        description="Reads data from state and updates an ArangoDB knowledge graph using the available tools.",
        instruction=instruction,
        tools=tools,
        output_key=output_key,
    )
