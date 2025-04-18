import json
from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_graph_agent(model, prompt, tools, data):
    """
    Constructs the GraphUpdateAgent with access to ArangoDB MCP tools.
    Returns an LlmAgent instance ready for execution.
    """
    prmt = load_prompt(prompt)
    return LlmAgent(
        model=model,
        name="GraphUpdateAgent",
        description="Updates an ArangoDB knowledge graph using the available tools.",
        instruction=prmt.replace("{data}", json.dumps(data, indent=2)),
        tools=tools,
    )
