from agno.team import Team
from agno.models.google import Gemini
from agents.ticket_fetcher import create_agent as fetcher
from agents.ticket_analyzer import create_agent as analyzer
from agents.seniority_estimator import create_agent as estimator


def create_team() -> Team:
    """
    Team created:
        OrgStructureTeam

    Purpose:
        Assembles a coordinate-style multi-agent Agno team composed of:
        - JiraFetcherAgent
        - JiraAnalyzerAgent
        - SeniorityEstimatorAgent

    Behavior:
        Runs the agents sequentially, passing structured output between them to produce an inferred org structure.
    """
    return Team(
        name="OrgStructureTeam",
        description="A coordinated team that extracts project/team structure and estimates developer seniority from Jira data.",
        model=Gemini(id="gemini-2.0-flash-exp"),
        mode="coordinate",
        members=[
            fetcher(),
            analyzer(),
            estimator(),
        ],
        show_tool_calls=True,
        markdown=True,
    )
