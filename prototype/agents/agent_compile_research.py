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
    1.  Listens for either DB_CHECK_DONE (if DB had data) or SEARCH_RESULTS_READY (if we had to do a web search).
    2.  Compiles research notes and publishes RESEARCH_COMPILED.
    """

    def __init__(self, name: str, state: OverallState, config: Dict[str, Any]):
        super().__init__(name, state)
        self.cfg = config

    async def handle_event(
        self, event: Event, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type in [EventType.DB_CHECK_DONE, EventType.SEARCH_RESULTS_READY]:
            self.report_status(
                ui_callback, f"Received {event.type.name}, compiling research notes..."
            )
            try:
                await self.compile_research(event_queue, ui_callback)
            except Exception as e:
                self.report_status(
                    ui_callback,
                    f"Research compilation failed critically: {e}",
                    type="error",
                )
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"ResearchAgent failed: {e}"},
                    ),
                    ui_callback,
                )

    async def compile_research(
        self, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        self.report_status(ui_callback, "Compiling research notes.")
        if not self.state.search_results:
            self.report_status(
                ui_callback,
                "No search results available to compile from. Skipping.",
                type="warning",
            )
            # Publish empty result (?)
            self.state.research = [""]
            await self.publish_event(
                event_queue, Event(EventType.RESEARCH_COMPILED), ui_callback
            )
            return

        # Fetch prompts
        try:
            system_prompt_text, research_template = get_prompt(
                self.cfg, system_id="RESEARCH_COMPILER", template_id="RESEARCH_PROMPT"
            )
            if not system_prompt_text or not research_template:
                raise ValueError("Missing required prompt templates for research.")

        except (KeyError, ValueError) as e:
            logger.error(f"Prompt configuration error: {e}", exc_info=True)
            self.report_status(ui_callback, f"Prompt config error: {e}", type="error")
            raise ValueError(f"Prompt configuration error: {e}") from e

        try:
            # Prepare LLM context
            self.report_status(
                ui_callback, "Formatting search results for LLM context..."
            )

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

            # Call LLM
            self.report_status(ui_callback, "Calling LLM for research compilation...")
            output = call_llm(messages=messages)
            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise Exception(f"LLM call failed: {output}")

            # Add research notes to state
            self.state.research = output
            self.report_status(ui_callback, "Research notes compiled successfully.")

            # Publish success event
            await self.publish_event(
                event_queue, Event(EventType.RESEARCH_COMPILED), ui_callback
            )

        except Exception as e:
            logger.error(
                f"Error during research compilation LLM call: {e}", exc_info=True
            )
            self.report_status(
                ui_callback, f"Research compilation failed: {e}", type="error"
            )
            raise e
