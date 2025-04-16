from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_story_agent(tools):
    """
    Constructs the StoryAgent with access to a custom Jira tool.
    Returns an LlmAgent instance ready for execution.
    """
    return LlmAgent(
        model="gemini-2.5-pro-exp-03-25",
        name="StoryAgent",
        description="Retrieves stories/tasks under each epic using jira_get_epic_issues",
        instruction=load_prompt("story_prompt"),
        tools=tools,
        output_key="stories_raw",
    )
