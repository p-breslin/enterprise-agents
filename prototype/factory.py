from typing import List

from .base_agent import BaseAgent
from .state import OverallState
from .agents.agent_check_database import DatabaseAgent
from .agents.agent_generate_queries import QueryGenerationAgent
from .agents.agent_web_search import WebSearchAgent
from .agents.agent_compile_research import ResearchAgent
from .agents.agent_extract_schema import ExtractionAgent

"""
Centralizes creation of agent instances. Each specialized agent is imported and instantiated, then returns them as a list to the orchestrator.
"""


def create_agents(state: OverallState) -> List[BaseAgent]:
    """
    Instantiates and configures all agent classes with the shared state.
    """

    agents: List[BaseAgent] = [
        DatabaseAgent(name="DatabaseAgent", state=state),
        QueryGenerationAgent(name="QueryGenerationAgent", state=state),
        WebSearchAgent(name="WebSearchAgent", state=state),
        ResearchAgent(name="ResearchAgent", state=state),
        ExtractionAgent(name="ExtractionAgent", state=state),
    ]
    return agents
