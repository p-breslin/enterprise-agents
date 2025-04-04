import json
import logging
from typing import Dict, Any, Optional, Callable

from .base_agent import BaseAgent
from utilities.LLM import call_llm
from utilities.helpers import format_results, get_prompt
from scripts.state import OverallState
from scripts.events import Event, EventType

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """
    Compiles structured research notes from search results or database entries.

    Behavior:
        1. Listens for DB_CHECK_DONE or SEARCH_RESULTS_READY.
        2. Formats search results and calls an LLM to generate a summary.
        3. Stores output in shared state and publishes RESEARCH_COMPILED event.
    """

    def __init__(self, name: str, state: OverallState, config: Dict[str, Any]):
        super().__init__(name, state)
        self.cfg = config

    async def handle_event(
        self,
        event: Event,
        event_queue,
        progress_callback: Optional[Callable[[Dict], None]],
    ) -> None:
        """
        Purpose:
            Entry point for the agent's behavior in response to events.
        Notes:
            Expects GRAPH_DATA_FOUND or SEARCH_RESULTS_READY as the trigger.
        """
        # Initialize progress manager
        self.setup_progress(progress_callback)

        if event.type in [EventType.GRAPH_DATA_FOUND, EventType.SEARCH_RESULTS_READY]:
            self.update_status(
                f"Received {event.type.name} event, compiling research notes..."
            )

            try:
                await self.compile_research(event_queue)
            except Exception as e:
                self.update_status(f"Research compilation failed: {e}", type_="error")
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"ResearchAgent failed: {e}"},
                    ),
                )

    async def compile_research(self, event_queue) -> None:
        """
        Purpose:
            Uses an LLM to compile research notes based on prior search results.
        Notes:
            Updates state.research and emits RESEARCH_COMPILED.
        """
        self.update_status("Compiling research notes...")

        if not self.state.search_results:
            self.update_status(
                "No search results found. Skipping research.", type_="warning"
            )
            self.state.research = [""]  # reconsider this?
            await self.publish_event(event_queue, Event(EventType.RESEARCH_COMPILED))
            return

        # Fetch system and user prompt templates
        try:
            system_prompt_text, research_template = get_prompt(
                self.cfg, system_id="RESEARCH_COMPILER", template_id="RESEARCH_PROMPT"
            )
            if not system_prompt_text or not research_template:
                raise ValueError("Missing required prompt templates for research.")

        except (KeyError, ValueError) as e:
            logger.error(f"Prompt configuration error: {e}", exc_info=True)
            self.update_status(f"Prompt config error: {e}", type_="error")
            raise ValueError(f"Prompt configuration error: {e}") from e

        # Format the messages for the LLM
        self.update_status("Formatting search results for LLM...")

        context_str = format_results(self.state.search_results)
        instructions = research_template.format(
            company=self.state.company,
            schema=json.dumps(self.state.output_schema, indent=2),
            context=context_str,
        )

        messages = [
            {"role": "system", "content": system_prompt_text},
            {"role": "user", "content": instructions},
        ]

        # Call the LLM
        try:
            self.update_status("Calling LLM for research compilation...")
            output = call_llm(messages=messages)

            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise RuntimeError(f"LLM call failed: {output}")

            self.state.research = output
            self.update_status("Research notes compiled successfully.")
            await self.publish_event(event_queue, Event(EventType.RESEARCH_COMPILED))

        except Exception as e:
            logger.error(
                f"LLM call failed during research compilation: {e}", exc_info=True
            )
            self.update_status(f"Research compilation failed: {e}", type_="error")
            raise e
