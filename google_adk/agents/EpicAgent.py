from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_epic_agent(tools, tool_debug=None):
    """
    Constructs the EpicAgent with access to Jira MCP tools.
    Returns:
        agent: LlmAgent instance ready for execution
        exit_stack: for closing the MCP connection safely
    """
    return LlmAgent(
        model="gemini-2.0-flash",
        name="EpicAgent",
        description="Fetches all Jira epics using the jira_search tool.",
        instruction=load_prompt("epic_prompt"),
        tools=tools,
        output_key="epics_raw",  # Will be saved to session.state["epics_raw"]
        before_tool_callback=tool_debug,
    )
