import logging
from typing import List, Dict, Any

from .state import OverallState
from agents.base_agent import BaseAgent
from agents.agent_check_database import DatabaseAgent
from agents.agent_generate_queries import QueryGenerationAgent
from agents.agent_web_search import WebSearchAgent
from agents.agent_compile_research import ResearchAgent
from agents.agent_extract_schema import ExtractionAgent

"""
Centralizes creation of agent instances. Each specialized agent is imported and instantiated, then returns them as a list to the orchestrator.
"""


def create_agents(state: OverallState, config: Dict[str, Any]) -> List[BaseAgent]:
    """
    Instantiates and configures all agent classes with the shared state and necessary configuration.
    """
    logger = logging.getLogger(__name__)
    logger.info("Creating agents...")

    agents: List[BaseAgent] = [
        DatabaseAgent(name="DatabaseAgent", state=state),
        QueryGenerationAgent(name="QueryGenerationAgent", state=state, config=config),
        WebSearchAgent(name="WebSearchAgent", state=state),
        ResearchAgent(name="ResearchAgent", state=state, config=config),
        ExtractionAgent(name="ExtractionAgent", state=state, config=config),
    ]
    logger.info(f"Created {len(agents)} agents.")
    return agents
