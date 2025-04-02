import abc
import logging
from typing import Dict, Optional, Callable
from scripts.events import Event
from scripts.state import OverallState

"""
Base class for all agents, defining the event handling interface and providing helper methods for logging and status reporting.

 - Defines a template for agents that handle events asynchronously.
 - Processes events delegated by the orchestrator.
 - Ensures subclasses implement handle_event; gives specific behavior to agents.
"""


class BaseAgent:
    """
    BaseAgent provides a common structure for all agents in the multi-agent system. Each agent subscribes to an asyncio Queue event bus and processes events as they arrive. Provides helpers for logging and reporting status to a UI via callback.
    """

    def __init__(self, name: str, state: OverallState):
        self.name = name  # agent's name
        self.state = state

    @abc.abstractmethod
    async def handle_event(
        self, event: Event, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        """
        Handles an event based on its type and payload. This is an Abstract Base Class (cannot be instantiated directly): agent classes must subclass BaseAgent and implement how to handle incoming events.

        - Should use report_status to communicate progress via the ui_callback.
        - Should use publish_event to send new events via the event_queue.

        Args:
            event (Event): The event to handle.
            event_queue (asyncio.Queue): The queue to publish new events to.
            ui_callback: Callback function to send status updates to the UI.
        """
        pass

    def report_status(
        self,
        ui_callback: Optional[Callable[[Dict], None]],
        message: str,
        type: str = "agent_action",  # Default type for agent activity
    ):
        """
        Logs a message and sends a status update dictionary to the UI callback, if provided. type is the type of status update (e.g., 'agent_action', 'agent_log', 'error')
        """
        # Log regardless of UI
        log_level = logging.ERROR if type == "error" else logging.INFO
        logging.log(log_level, f"[{self.name}] {message}")

        if ui_callback:
            try:
                # Send structured update
                status_update = {
                    "type": type,
                    "agent_name": self.name,
                    "message": message,
                }
                ui_callback(status_update)
            except Exception as e:
                # Log callback error but don't crash the agent
                logging.warning(
                    f"[{self.name}] UI callback failed during report_status: {e}",
                    exc_info=False,
                )

    def log(self, message: str):
        """
        Simple internal logging without sending to UI.
        Keeps log separate for purely internal logging.
        Maybe not needed!
        """
        logging.info(f"[{self.name}] {message}")

    async def publish_event(
        self, event_queue, event: Event, ui_callback: Optional[Callable[[Dict], None]]
    ):
        """
        Helper method to publish an event to the queue and report the action via the UI callback.
        """
        # Report the intention BEFORE putting on queue
        self.report_status(
            ui_callback, f"Publishing event: {event.type.name}", type="event"
        )
        await event_queue.put(event)
