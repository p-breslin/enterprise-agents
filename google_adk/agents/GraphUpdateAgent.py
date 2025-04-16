from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_graph_agent(model, prompt, tools):
    """
    Constructs the GraphUpdateAgent with access to ArangoDB MCP tools.
    Returns an LlmAgent instance ready for execution.
    """
    return LlmAgent(
        model=model,
        name="GraphUpdateAgent",
        description="Updates an ArangoDB knowledge graph using the available tools.",
        instruction=load_prompt(prompt),
        tools=tools,
        output_key="graph_raw",
    )
