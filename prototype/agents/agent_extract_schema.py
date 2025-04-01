import json
import logging
from typing import Dict, Any

from .base_agent import BaseAgent
from utilities.LLM import call_llm
from utilities.helpers import get_prompt, get_api_key
from scripts.state import OverallState
from scripts.events import Event, EventType

logger = logging.getLogger(__name__)


class ExtractionAgent(BaseAgent):
    """
    1.  Listens for RESEARCH_COMPILED. When triggered:
    2.  Finalizes the JSON extraction.
    3.  Publishes EXTRACTION_COMPLETE.
    """

    def __init__(self, name: str, state: OverallState, config: Dict[str, Any]):
        super().__init__(name, state)
        self.cfg = config

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.RESEARCH_COMPILED:
            self.log(f"Received {event.type.name} event.")
            await self.extract_schema(event_queue)

    async def extract_schema(self, event_queue) -> None:
        self.log("Extracting notes into JSON schema.")

        if not self.state.research:
            # Handle empty research notes
            self.state.final_output = {}
            self.state.complete = True
            logger.warning(
                "No research notes found, setting final output to empty dict."
            )
            await event_queue.put(Event(EventType.EXTRACTION_COMPLETE))
            return

        # Fetch prompts
        try:
            system_prompt_text = get_prompt(self.cfg, system_id="SCHEMA_EXTRACTOR")

            extraction_template = get_prompt(self.cfg, system_id="EXTRACTION_PROMPT")

        except KeyError as e:
            logger.error(
                f"Missing required prompt configuration key: {e}", exc_info=True
            )
            return

        # LLM context
        instructions = extraction_template.format(
            schema=json.dumps(self.state.output_schema, indent=2),
            research=self.state.research,
        )

        messages = [
            {"role": "system", "content": system_prompt_text},
            {"role": "user", "content": instructions},
        ]

        # API key
        openai_api_key = get_api_key(service="OPENAI")

        # Call LLM
        try:
            output = call_llm(
                openai_api_key,
                messages=messages,
                json_mode=True,
            )
            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise Exception(f"LLM call failed: {output}")

            try:
                data = json.loads(output)
                self.state.final_output = data
                self.state.complete = True
                self.log("Final output successfully parsed as JSON.")

            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse JSON from LLM response: {json_err}")
                logger.debug(f"Failed LLM response content: {output}")
                self.state.final_output = {
                    "error": "Failed to parse LLM output as JSON",
                    "raw_output": output,
                }
                self.state.complete = False
                await event_queue.put(Event(EventType.EXTRACTION_COMPLETE))
                return

        except Exception as e:
            logger.error(f"Error during schema extraction LLM call: {e}", exc_info=True)
            self.state.final_output = {"error": f"Schema Extraction Failed: {e}"}
            self.state.complete = False
            await event_queue.put(Event(EventType.EXTRACTION_COMPLETE))
            return

        self.log("Publishing EXTRACTION_COMPLETE.")
        await event_queue.put(Event(EventType.EXTRACTION_COMPLETE))
