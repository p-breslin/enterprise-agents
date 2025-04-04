import logging
from typing import Dict, Optional, Callable


class ProgressManager:
    """
    Manages progress updates from the agents and/or the system.
    """

    def __init__(
        self, agent_name: str, progress: Optional[Callable[[Dict], None]] = None
    ):
        self.agent_name = agent_name
        self.progress = progress

    def send(
        self,
        message: str,
        type_: str = "agent_action",
        event_type: Optional[str] = None,
    ):
        log_level = logging.ERROR if type_ == "error" else logging.INFO
        logging.log(log_level, f"[{self.agent_name}] {message}")
        if self.progress:
            try:
                update = {
                    "type": type_,
                    "agent_name": self.agent_name,
                    "message": message,
                    "event_type": event_type,
                }
                self.progress(update)
            except Exception as e:
                logging.warning(
                    f"[{self.agent_name}] Progress update failed: {e}", exc_info=False
                )

    def publish_event(self, event_name: str):
        self.send("Publishing event:", type_="event", event_type=event_name)
