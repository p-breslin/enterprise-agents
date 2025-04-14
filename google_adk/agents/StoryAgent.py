from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def get_story_agent(tools, tool_debug=None, model_debug=None):
    """
    Constructs the StoryAgent with access to Jira MCP tools.
    Returns an LlmAgent instance ready for execution.
    """
    return LlmAgent(
        model="gemini-2.0-flash-lite",
        name="StoryAgent",
        description="Retrieves stories/tasks under each epic using jira_get_epic_issues",
        instruction=load_prompt("story_prompt"),
        tools=tools,
        output_key="stories_raw",
        before_tool_callback=tool_debug,
        before_model_callback=model_debug
    )
