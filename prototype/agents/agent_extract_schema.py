import json
import logging
from typing import Dict, Any, Optional, Callable

from .base_agent import BaseAgent
from utilities.LLM import call_llm
from utilities.helpers import get_prompt
from scripts.state import OverallState
from scripts.events import Event, EventType

logger = logging.getLogger(__name__)


class ExtractionAgent(BaseAgent):
    """
    Converts research notes into structured JSON output that matches the target schema as defined in the configuration.

    Behavior:
        1. Listens for RESEARCH_COMPILED events.
        2. Extracts structured data using an LLM.
        3. Stores result in state.final_output and publishes the EXTRACTION_COMPLETE event.
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
            Expects RESEARCH_COMPILED as the trigger.
        """
        # Initialize progress manager
        self.setup_progress(progress_callback)

        if event.type == EventType.RESEARCH_COMPILED:
            self.update_status("Received RESEARCH_COMPILED, extracting schema...")

            try:
                await self.extract_schema(event_queue)
            except Exception as e:
                self.update_status(f"Schema extraction failed: {e}", type_="error")
                self.state.final_output = {"error": f"Schema Extraction Failed: {e}"}
                await self.publish_event(
                    event_queue, Event(EventType.EXTRACTION_COMPLETE)
                )

    async def extract_schema(self, event_queue) -> None:
        """
        Purpose:
            Converts compiled research notes into a structured JSON format using an LLM.
        Notes:
            Updates self.state.final_output and emits EXTRACTION_COMPLETE.
        """
        self.update_status("Extracting notes into structured JSON...")

        # Handle empty or badly formatted research notes
        if not isinstance(self.state.research, str) or not self.state.research.strip():
            self.update_status(
                "No valid research notes found. Skipping extraction.", type_="warning"
            )
            self.state.final_output = {}
            await self.publish_event(event_queue, Event(EventType.EXTRACTION_COMPLETE))
            return

        # Fetch system and user prompt templates
        try:
            system_prompt_text, extraction_template = get_prompt(
                self.cfg, system_id="SCHEMA_EXTRACTOR", template_id="EXTRACTION_PROMPT"
            )
            if not system_prompt_text or not extraction_template:
                raise ValueError(
                    "Missing required prompt templates for schema extraction."
                )

        except (KeyError, ValueError) as e:
            logger.error(f"Prompt configuration error: {e}", exc_info=True)
            self.update_status(f"Prompt config error: {e}", type_="error")
            raise ValueError(f"Prompt configuration error: {e}") from e

        # Format the messages for the LLM
        instructions = extraction_template.format(
            schema=json.dumps(self.state.output_schema, indent=2),
            research=self.state.research.strip(),
        )
        messages = [
            {"role": "system", "content": system_prompt_text},
            {"role": "user", "content": instructions},
        ]

        # Call the LLM
        try:
            self.update_status("Calling LLM for schema extraction...")
            output = call_llm(messages=messages, json_mode=True)

            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise RuntimeError(f"LLM call failed: {output}")

            try:
                data = json.loads(output)
                self.state.final_output = data
                self.update_status("Successfully parsed final output as JSON.")

            except json.JSONDecodeError as json_err:
                logger.error(
                    f"Failed to parse LLM JSON output: {json_err}", exc_info=True
                )
                logger.debug(f"Failed LLM output: {output}")

                self.update_status(
                    f"Failed to parse LLM JSON output: {json_err}", type_="error"
                )
                self.state.final_output = {
                    "error": f"Failed to parse LLM output as JSON: {json_err}",
                    "raw_output": output,
                }

        except Exception as e:
            logger.error(f"Error during schema extraction: {e}", exc_info=True)
            self.update_status(f"Schema extraction failed: {e}", type_="error")
            self.state.final_output = {"error": f"Schema Extraction Failed: {e}"}

        await self.publish_event(event_queue, Event(EventType.EXTRACTION_COMPLETE))
