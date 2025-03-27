import abc
import logging
from .events import Event
from .state import OverallState

"""
========
Summary:
========
 - Defines a template for agents that handle events asynchronously.
 - Processes events delegated by the orchestrator.
 - Ensures subclasses implement handle_event; gives specific behavior to agents.
"""


class BaseAgent:
    """
    BaseAgent provides a common structure for all agents in the multi-agent system. Each agent subscribes to an asyncio Queue event bus and processes events as they arrive.
    """

    def __init__(self, name: str, state: OverallState):
        self.name = name  # agent's name
        self.state = state

    @abc.abstractmethod
    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Handles an event based on its type and payload. This is an Abstract Base Class (cannot be instantiated directly): agent classes must subclass BaseAgent and implement how to handle incoming events.
        """
        pass

    def log(self, message: str):
        logging.info(f"[{self.name}] {message}")
