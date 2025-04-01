import json
import logging
from typing import Dict, Any

from .base_agent import BaseAgent
from utilities.LLM import call_llm
from utilities.helpers import format_results, get_prompt, get_api_key
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

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type in [EventType.DB_CHECK_DONE, EventType.SEARCH_RESULTS_READY]:
            self.log(f"Received {event.type.name} event.")
            await self.compile_research(event_queue)

    async def compile_research(self, event_queue) -> None:
        self.log("Compiling research notes.")
        if not self.state.search_results:
            logger.warning("No search results available to compile research from.")
            return

        # Fetch prompts
        try:
            system_prompt_text = get_prompt(self.cfg, system_id="RESEARCH_COMPILER")

            research_template = get_prompt(self.cfg, system_id="RESEARCH_PROMPT")

        except KeyError as e:
            logger.error(
                f"Missing required prompt configuration key: {e}", exc_info=True
            )
            return

        # LLM context
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

        # API key
        openai_api_key = get_api_key(service="OPENAI")

        # Call LLM
        try:
            output = call_llm(openai_api_key, messages=messages)
            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise Exception(f"LLM call failed: {output}")

            self.state.research.append(output)
            self.log("Reesearch notes completed.")
            self.log("Publishing RESEARCH_COMPILED.")
            await event_queue.put(Event(EventType.RESEARCH_COMPILED))

        except Exception as e:
            logger.error(
                f"Error during research compilation LLM call: {e}", exc_info=True
            )
