from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_graph_agent(tools):
    """
    Constructs the GraphUpdateAgent with access to ArangoDB MCP tools.
    Returns an LlmAgent instance ready for execution.
    """
    return LlmAgent(
        model="gemini-2.5-pro-exp-03-25",
        name="GraphUpdateAgent",
        description="Updates an ArangoDB knowledge graph using the available tools.",
        instruction=load_prompt("epic_graph_prompt"),
        tools=tools,
        output_key="graph_raw",
    )
