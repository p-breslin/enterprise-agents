import re
import json
import logging
from typing import Dict, Any
from .base_agent import BaseAgent

from utilities.LLM import call_llm
from utilities.helpers import get_prompt, get_api_key
from scripts.state import OverallState
from scripts.events import Event, EventType

logger = logging.getLogger(__name__)


class QueryGenerationAgent(BaseAgent):
    """
    1.  Listens for NEED_QUERIES. When triggered:
    2.  Generates queries via the LLM and stores them in state.search_queries.
    3.  Publishes QUERIES_GENERATED.
    """

    def __init__(self, name: str, state: OverallState, config: Dict[str, Any]):
        super().__init__(name, state)
        self.cfg = config

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.NEED_EXTERNAL_DATA:
            self.log(f"Received {event.type.name} event.")
            await self.generate_queries(event_queue)

    async def generate_queries(self, event_queue) -> None:
        """
        Generates search queries using LLM.
        """
        self.log(f"Generating search queries for {self.state.company}.")

        # Runtime settings from config
        runtime_settings = self.cfg.get("runtime_settings", {})
        n_searches = runtime_settings.get("N_searches", 1)
        self.log(f"Using N_searches = {n_searches}")

        try:
            system_prompt_text = get_prompt(self.cfg, system_id="QUERY_GENERATOR")

            query_gen_template = get_prompt(
                self.cfg, system_id="QUERY_GENERATOR_PROMPT"
            )

            query_list_template = get_prompt(self.cfg, system_id="QUERY_LIST_PROMPT")

        except KeyError as e:
            logger.error(
                f"Missing required prompt configuration key: {e}", exc_info=True
            )
            return

        # Messages for LLM
        context_instructions = query_gen_template.format(
            company=self.state.company,
            schema=json.dumps(self.state.output_schema, indent=2),
            N_searches=n_searches,
        )
        output_format_instructions = query_list_template.format(N_searches=n_searches)

        messages = [
            {"role": "system", "content": system_prompt_text},
            {"role": "user", "content": context_instructions},
            {"role": "user", "content": output_format_instructions},
        ]

        # Get API key
        openai_api_key = get_api_key(service="OPENAI")

        # Call LLM
        try:
            output = call_llm(openai_api_key, messages=messages)
            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise Exception(f"LLM call failed: {output}")

            # Clean search queries from output (not necessary for good models)
            search_queries = re.findall(r'"\s*(.*?)\s*"', output)
            self.state.search_queries = search_queries
            self.log(f"Generated search queries: {self.state.search_queries}")

            self.log("Publishing QUERIES_GENERATED.")
            await event_queue.put(Event(EventType.QUERIES_GENERATED))

        except Exception as e:
            logger.error(
                f"Error during query generation LLM call or processing: {e}",
                exc_info=True,
            )
