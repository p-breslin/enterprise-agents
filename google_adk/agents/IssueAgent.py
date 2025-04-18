from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_issue_agent(model, tools, input_key, output_key=None):
    """
    Constructs the IssueAgent with access to Jira MCP tools.
    Returns an LlmAgent instance ready for execution.
    """
    prompt = load_prompt("issue_prompt")
    instruction = prompt.replace("{state_key_name}", input_key)
    return LlmAgent(
        model=model,
        name="IssueAgent",
        description="Reads story data from state and fetches metadata from Jira issues using the jira_get_issue tool.",
        instruction=instruction,
        tools=tools,
        output_key=output_key,
    )
