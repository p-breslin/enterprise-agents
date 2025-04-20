from agno.agent import Agent
from schemas import IssueList
from utils_agno import load_prompt


def build_issue_agent(model, tools, input_state_key: str):
    """
    Constructs the IssueAgent using Agno Agent.
     - Reads story data from workflow session_state.
     - Returns an Agno Agent instance ready for execution.
    """
    prompt_template = load_prompt("issue_prompt")
    instruction_text = prompt_template.replace("{state_key_name}", input_state_key)

    return Agent(
        model=model,
        name="IssueAgent",
        description=f"Reads story data from state key '{input_state_key}' and fetches metadata from Jira issues using available tools.",
        instructions=[instruction_text],
        tools=tools,
        add_state_in_messages=True,  # Enable agent access to session_state
        response_model=IssueList,  # Expecting structured output
        markdown=False,  # Output should be JSON
    )
