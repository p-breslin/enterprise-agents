import json
from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_story_agent(model, tools, data, output_key=None):
    """
    Constructs the StoryAgent with access to a custom Jira tool.
    Returns an LlmAgent instance ready for execution.
    """
    prompt = load_prompt("story_prompt")
    return LlmAgent(
        model=model,
        name="StoryAgent",
        description="Retrieves stories/tasks under each epic using jira_get_epic_issues",
        instruction=prompt.replace("{data}", json.dumps(data, indent=2)),
        tools=tools,
        output_key=output_key
    )
