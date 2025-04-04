import re
import json
import logging
from typing import Dict, Any, Optional, Callable

from .base_agent import BaseAgent
from utilities.LLM import call_llm
from utilities.helpers import get_prompt
from scripts.state import OverallState
from scripts.events import Event, EventType

logger = logging.getLogger(__name__)


class QueryGenerationAgent(BaseAgent):
    """
    Generates search queries to be used to gather online information via web searches.

    Behavior:
        1. Listens for NEED_EXTERNAL_DATA.
        2. Uses an LLM to generate a list of schema-relevant queries.
        3. Stores queries in shared state and publishes QUERIES_GENERATED.
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
            Expects NEED_EXTERNAL_DATA as the trigger.
        """
        # Initialize progress manager
        self.setup_progress(progress_callback)

        if event.type == EventType.NEED_EXTERNAL_DATA:
            self.update_status(
                "Received NEED_EXTERNAL_DATA event, generating search queries..."
            )

            try:
                await self.generate_queries(event_queue)
            except Exception as e:
                self.update_status(f"Query generation failed: {e}", type_="error")
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"QueryGenerationAgent failed: {e}"},
                    ),
                )

    async def generate_queries(self, event_queue) -> None:
        """
        Purpose:
            Uses an LLM to generate search queries based on a target schema (as defined in configs) and the user-defined company name.

        Notes:
            Stores results in state.search_queries and triggers the QUERIES_GENERATED event.
        """
        self.update_status(f"Generating search queries for: {self.state.company}")

        # Runtime settings from config
        runtime_settings = self.cfg.get("runtime_settings", {})
        n_searches = runtime_settings.get("N_searches", 1)
        self.update_status(f"Targeting {n_searches} queries.")

        # Fetch the system and user prompt templates
        try:
            system_prompt_text, query_gen_template = get_prompt(
                self.cfg,
                system_id="QUERY_GENERATOR",
                template_id="QUERY_GENERATOR_PROMPT",
            )

            # Using two user prompts for separating context from constraints
            _, query_list_template = get_prompt(
                self.cfg, template_id="QUERY_LIST_PROMPT"
            )

        except (KeyError, ValueError) as e:
            logger.error(f"Prompt configuration error: {e}", exc_info=True)
            self.update_status(f"Prompt config error: {e}", type_="error")
            raise ValueError(f"Prompt configuration error: {e}") from e

        # Format the messages for the LLM
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

        # Call the LLM
        try:
            self.update_status("Calling the LLM for query generation...")
            output = call_llm(messages=messages)

            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise RuntimeError(f"LLM call failed: {output}")

            # Clean search queries from output (not necessary for good models)
            search_queries = re.findall(r'"\s*(.*?)\s*"', output)
            if not search_queries:
                logger.warning(f"Unexpected LLM output format: {output}")
                raise ValueError("LLM did not generate queries in the expected format.")

            self.update_status(f"Generated {len(search_queries)} searches.")
            self.update_status(f"Queries: {search_queries}", type_="agent_log")

            self.state.search_queries = search_queries
            await self.publish_event(event_queue, Event(EventType.QUERIES_GENERATED))

        except Exception as e:
            logger.error(f"Query generation failed: {e}", exc_info=True)
            self.update_status(f"Query generation failed: {e}", type_="error")
            raise e
