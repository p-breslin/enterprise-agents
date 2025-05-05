import logging
from pydantic import BaseModel
from typing import List, Any, Dict, Optional, Type

from utils.helpers import load_config
from .BaseAgent import _build_base_agent
from models.schemas import (
    EpicList,
    StoryList,
    IssueList,
    RepoList,
    PRNumbers,
    PRDetails,
    PRCommits,
)

log = logging.getLogger(__name__)


# Response model (schema) mapping
SCHEMA_MAP: Dict[str, Type[BaseModel]] = {
    "EpicList": EpicList,
    "StoryList": StoryList,
    "IssueList": IssueList,
    "RepoList": RepoList,
    "PRNumbers": PRNumbers,
    "PRDetails": PRDetails,
    "PRCommits": PRCommits,
}

# Load agent configurations
agent_cfgs = load_config(file="agents")


def build_agent(
    agent_type: str,
    model: str,
    tools: List[Any],
    prompt_key: Optional[str] = None,
    initial_state: Optional[Dict[str, Any]] = None,
    response_model: bool = False,
    debug: bool = False,
):
    """
    Builds an agent based on the predefined configuration type.
    """
    cfg = agent_cfgs.get(agent_type)
    if not cfg:
        log.error(f"No configuration found for agent type: {agent_type}")
        raise ValueError(f"Invalid agent type: {agent_type}")

    # Check if initial state is required but not provided
    if cfg.get("requires_initial_state", False) and initial_state is None:
        log.error(
            f"Agent type '{agent_type}' requires initial_state, but none was provided."
        )
        raise ValueError(f"Agent type '{agent_type}' requires initial_state.")

    log.info(f"Building Agent: {cfg.get('name', agent_type)} (Type: {agent_type})")

    schema_model = None
    if response_model:
        # Resolve Pydantic response model (schema) name to class type
        schema_name = cfg.get("schema")
        if schema_name:
            schema_model = SCHEMA_MAP.get(schema_name)
            if not schema_model:
                log.warning(f"'{schema_name}' schema for '{agent_type}' not found.")

    # Extract prompt key
    if not prompt_key:
        prompt_key = cfg.get("prompt_key")

    return _build_base_agent(
        model=model,
        tools=tools,
        name=cfg["name"],
        description=cfg["description"],
        prompt_key=prompt_key,
        response_model=schema_model,
        initial_state=initial_state,
        markdown=cfg["markdown"],
        debug=debug,
    )
