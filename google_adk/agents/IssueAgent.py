from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_issue_agent(model, tools):
    """
    Constructs the IssueAgent with access to Jira MCP tools.
    Returns an LlmAgent instance ready for execution.
    """
    return LlmAgent(
        model=model,
        name="IssueAgent",
        description="Fetches metadata from Jira issues using the jira_get_issue tool.",
        instruction=load_prompt("issue_prompt"),
        tools=tools,
        output_key="issues_raw",
    )
