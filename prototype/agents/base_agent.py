import abc
import logging
from typing import Dict, Optional, Callable

from scripts.events import Event
from scripts.state import OverallState
from utilities.progress_manager import ProgressManager

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Provides a common agent structure that all agents inherit. Each agent subscribes to an event queue and processes events as they arrive.

    - Defines a template for agents that handle events asynchronously.
    - Processes events delegated by the orchestrator.
    - Shared logic for logging, progress reporting, and event publishing.
    """

    def __init__(self, name: str, state: OverallState):
        self.name = name
        self.state = state
        self.progress: Optional[ProgressManager] = None

    def setup_progress(self, progress_callback: Optional[Callable[[Dict], None]]):
        """
        Purpose:
            Initializes a ProgressManager instance for sending updates.
        Notes:
            Should be called at the start of every handle_event() in agent subclasses.
        """
        self.progress = ProgressManager(self.name, progress_callback)

    def update_status(self, message: str = None, type_: str = "agent_action"):
        """
        Purpose:
            Reports status updates to the UI through the ProgressManager.
        """
        if self.progress:
            self.progress.send(message, type_)

    async def publish_event(self, event_queue, event: Event, announce: bool = True):
        """
        Purpose:
            Puts a new event onto the shared event queue. Optionally announces this to the UI via ProgressManager.
        """
        if self.progress and announce:
            self.update_status(message=f"Publishing event: {event.type.name}")
        await event_queue.put(event)

    def log(self, message: str):
        """
        Purpose:
            Logs a message directly without triggering a UI update.
        Notes:
            This is for testing purposes and will probably be removed.
        """
        logging.info(f"[{self.name}] {message}")

    @abc.abstractmethod
    async def handle_event(
        self,
        event: Event,
        event_queue,
        progress_callback: Optional[Callable[[Dict], None]],
    ) -> None:
        """
        Purpose:
            Receives an event, decides what to do, and optionally pushes new events.
        Notes:
            This is an Abstract Base Class (cannot be instantiated directly): agent classes must subclass BaseAgent and implement how to handle incoming events i.e. this must be implemented by each agent.

        """
        pass
