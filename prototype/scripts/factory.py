import logging
from typing import List, Dict, Any, Optional

from .state import OverallState
from agents.base_agent import BaseAgent
from agents.agent_query_graph import GraphQueryAgent
from agents.agent_generate_queries import QueryGenerationAgent
from agents.agent_web_search import WebSearchAgent
from agents.agent_compile_research import ResearchAgent
from agents.agent_extract_schema import ExtractionAgent
from agents.agent_graph_update import GraphUpdateAgent
from utilities.graph_db import ArangoDBManager


"""
Centralizes creation of agent instances. Each specialized agent is imported and instantiated, then returns them as a list to the orchestrator.
"""
logger = logging.getLogger(__name__)


def create_agents(
    state: OverallState,
    config: Dict[str, Any],
    arangodb_manager: Optional[ArangoDBManager],
) -> List[BaseAgent]:
    """
    Instantiates and configures all agent classes with the shared state, necessary configuration, and ArangoDB manager.
    """

    logger.info("Creating agents...")

    agents: List[BaseAgent] = [
        GraphQueryAgent(
            name="GraphQueryAgent", state=state, arangodb_manager=arangodb_manager
        ),
        QueryGenerationAgent(name="QueryGenerationAgent", state=state, config=config),
        WebSearchAgent(name="WebSearchAgent", state=state, config=config),
        ResearchAgent(name="ResearchAgent", state=state, config=config),
        ExtractionAgent(name="ExtractionAgent", state=state, config=config),
        GraphUpdateAgent(
            name="GraphUpdateAgent",
            state=state,
            config=config,
            arangodb_manager=arangodb_manager,
        ),
    ]
    logger.info(f"Created {len(agents)} agents.")
    return agents


# --- To be added ---
# GraphUpdateAgent(name="GraphUpdateAgent", state=state, config=config, arangodb_manager=arangodb_manager),
