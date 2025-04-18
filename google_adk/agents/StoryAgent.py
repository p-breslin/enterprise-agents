from google_adk.utils_adk import load_prompt
from google.adk.agents.llm_agent import LlmAgent


def build_story_agent(model, tools, input_key, output_key=None):
    """
    Constructs the StoryAgent with access to a custom Jira tool.
    Returns an LlmAgent instance ready for execution.
    """
    prompt = load_prompt("story_prompt")
    instruction = prompt.replace("{state_key_name}", input_key)
    return LlmAgent(
        model=model,
        name="StoryAgent",
        description="Reads epic data from state and retrieves stories/tasks under each epic using jira_get_epic_issues",
        instruction=instruction,
        tools=tools,
        output_key=output_key,
    )
