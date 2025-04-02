import re
import json
import logging
from typing import Dict, Any, Optional, Callable
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

    async def handle_event(
        self, event: Event, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.NEED_EXTERNAL_DATA:
            self.report_status(
                ui_callback, f"Received {event.type.name}, generating search queries..."
            )
            try:
                await self.generate_queries(event_queue, ui_callback)
            except Exception as e:
                self.report_status(
                    ui_callback,
                    f"Query generation failed critically: {e}",
                    type="error",
                )
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"QueryGenerationAgent failed: {e}"},
                    ),
                    ui_callback,
                )

    async def generate_queries(
        self, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        """
        Generates search queries using LLM.
        """
        self.report_status(
            ui_callback, f"Generating search queries for {self.state.company}."
        )

        # Runtime settings from config
        runtime_settings = self.cfg.get("runtime_settings", {})
        n_searches = runtime_settings.get("N_searches", 1)
        self.report_status(ui_callback, f"Targeting {n_searches} queries.")

        # Fetch prompts (two user prompts; separating context from constraints)
        try:
            system_prompt_text, query_gen_template = get_prompt(
                self.cfg,
                system_id="QUERY_GENERATOR",
                template_id="QUERY_GENERATOR_PROMPT",
            )

            _, query_list_template = get_prompt(
                self.cfg, template_id="QUERY_LIST_PROMPT"
            )

        except (KeyError, ValueError) as e:
            logger.error(f"Prompt configuration error: {e}", exc_info=True)
            self.report_status(ui_callback, f"Prompt config error: {e}", type="error")

            # Can't proceed without prompts
            raise ValueError(f"Prompt configuration error: {e}") from e

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
            self.report_status(ui_callback, "Calling LLM for query generation...")
            output = call_llm(openai_api_key, messages=messages)
            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise Exception(f"LLM call failed: {output}")

            # Clean search queries from output (not necessary for good models)
            search_queries = re.findall(r'"\s*(.*?)\s*"', output)
            if not search_queries:
                logger.warning(
                    f"LLM output did not contain expected query format. Output: {output}"
                )
                raise ValueError("LLM did not generate queries in the expected format.")

            self.state.search_queries = search_queries
            self.report_status(
                ui_callback,
                f"Generated {len(self.state.search_queries)} search queries.",
            )
            self.report_status(
                ui_callback, f"Queries: {self.state.search_queries}", type="agent_log"
            )
            await self.publish_event(
                event_queue, Event(EventType.QUERIES_GENERATED), ui_callback
            )

        except Exception as e:
            logger.error(
                f"Error during query generation LLM call or processing: {e}",
                exc_info=True,
            )
            self.report_status(
                ui_callback, f"Query generation failed: {e}", type="error"
            )
            raise e
