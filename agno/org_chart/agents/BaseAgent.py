import logging
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Type

from agno.agent import Agent
from utils.helpers import load_prompt

log = logging.getLogger(__name__)


def _build_base_agent(
    model: Any,
    tools: List[Any],
    name: str,
    description: str,
    prompt_key: str,
    response_model: Optional[Type[BaseModel]] = None,
    initial_state: Optional[Dict[str, Any]] = None,
    markdown: bool = False,
    debug: bool = False,
) -> Agent:
    """Internal helper to build configured Agno Agents."""
    try:
        instruction_text = load_prompt(prompt_key)
    except KeyError:
        log.error(f"Prompt key '{prompt_key}' not found.")
        raise ValueError(f"Invalid prompt key: {prompt_key}")

    agent_args = {
        "model": model,
        "tools": tools,
        "name": name,
        "description": description,
        "instructions": [instruction_text],
        "response_model": response_model,
        "markdown": markdown,
        "debug_mode": debug,
        "show_tool_calls": debug,
    }

    if initial_state is not None:
        agent_args["session_state"] = initial_state
        agent_args["add_state_in_messages"] = True  # access to session_state
        log.debug(
            f"Agent '{name}' initialized with state keys: {list(initial_state.keys())}"
        )

    log.info(f"Building Agent: {name} with prompt: {prompt_key}")
    return Agent(**agent_args)
