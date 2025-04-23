from agno.agent import Agent
from schemas import IssueList
from utils_agno import load_prompt


def build_issue_agent(
    model, tools, initial_state: str, prompt="issue_prompt", debug=False
):
    """
    Constructs the IssueAgent using Agno Agent.
     - Reads story data from workflow session_state.
     - Returns an Agno Agent instance ready for execution.
    """
    instruction_text = load_prompt(prompt)
    return Agent(
        model=model,
        name="IssueAgent",
        description="Reads story data provided and fetches metadata from Jira issues using available tools.",
        instructions=[instruction_text],
        tools=tools,
        session_state=initial_state,
        add_state_in_messages=True,  # Enable agent access to session_state
        response_model=IssueList,  # Expecting structured output
        markdown=False,  # Output should be JSON
        debug_mode=debug,
    )
