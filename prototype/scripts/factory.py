import logging
from typing import List, Dict, Any, Optional

from .state import OverallState
from utilities.graph_db import ArangoDBManager

from agents.base_agent import BaseAgent
from agents.agent_query_graph import GraphQueryAgent
from agents.agent_generate_queries import QueryGenerationAgent
from agents.agent_web_search import WebSearchAgent
from agents.agent_compile_research import ResearchAgent
from agents.agent_extract_schema import ExtractionAgent
from agents.agent_graph_update import GraphUpdateAgent

logger = logging.getLogger(__name__)


def create_agents(
    state: OverallState,
    config: Dict[str, Any],
    arangodb_manager: Optional[ArangoDBManager],
) -> List[BaseAgent]:
    """
    Purpose:
        Centralizes creation of agent instances. Instantiates and configures all pipeline agents with shared state and configuration.
    Notes:
        - Keeps orchestration logic decoupled.
        - ArangoDBManager is required for graph-related agents.
    """
    logger.info("Creating agents...")

    return [
        GraphQueryAgent(
            name="GraphQueryAgent",
            state=state,
            arangodb_manager=arangodb_manager,
        ),
        QueryGenerationAgent(
            name="QueryGenerationAgent",
            state=state,
            config=config,
        ),
        WebSearchAgent(
            name="WebSearchAgent",
            state=state,
            config=config,
        ),
        ResearchAgent(
            name="ResearchAgent",
            state=state,
            config=config,
        ),
        ExtractionAgent(
            name="ExtractionAgent",
            state=state,
            config=config,
        ),
        GraphUpdateAgent(
            name="GraphUpdateAgent",
            state=state,
            config=config,
            arangodb_manager=arangodb_manager,
        ),
    ]
