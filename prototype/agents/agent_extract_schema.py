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
    1.  Listens for RESEARCH_COMPILED. When triggered:
    2.  Finalizes the JSON extraction.
    3.  Publishes EXTRACTION_COMPLETE.

    Reports status via UI callback.
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
        if event.type == EventType.RESEARCH_COMPILED:
            self.report_status(
                ui_callback, f"Received {event.type.name}, extracting schema..."
            )
            try:
                await self.extract_schema(event_queue, ui_callback)
            except Exception as e:
                self.report_status(
                    ui_callback,
                    f"Schema extraction failed critically: {e}",
                    type="error",
                )
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"ExtractionAgent failed: {e}"},
                    ),
                    ui_callback,
                )

    async def extract_schema(
        self, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        self.report_status(ui_callback, "Extracting notes into JSON schema.")

        if (
            not self.state.research
            or not isinstance(self.state.research, str)
            or not self.state.research.strip()
        ):
            # Handle empty research notes
            self.report_status(
                ui_callback,
                "No research notes found. Skipping extraction.",
                type="warning",
            )
            self.state.final_output = {}  # Set to empty dict for consistency
            await self.publish_event(
                event_queue, Event(EventType.EXTRACTION_COMPLETE), ui_callback
            )
            return

        # Fetch prompts
        try:
            system_prompt_text, extraction_template = get_prompt(
                self.cfg, system_id="SCHEMA_EXTRACTOR", template_id="EXTRACTION_PROMPT"
            )
            if not system_prompt_text or not extraction_template:
                raise ValueError(
                    "Missing required prompt templates for schema extraction."
                )

        except (KeyError, ValueError) as e:
            logger.error(
                f"Missing required prompt configuration key: {e}", exc_info=True
            )
            logger.error(f"Prompt configuration error: {e}", exc_info=True)
            self.report_status(ui_callback, f"Prompt config error: {e}", type="error")
            raise ValueError(f"Prompt configuration error: {e}") from e

        # Prepare LLM context
        try:
            # Ensure research is a string for the prompt (maybe not needed)
            research_text = (
                str(self.state.research)
                if not isinstance(self.state.research, str)
                else self.state.research
            )

            instructions = extraction_template.format(
                schema=json.dumps(self.state.output_schema, indent=2),
                research=research_text,
            )

            messages = [
                {"role": "system", "content": system_prompt_text},
                {"role": "user", "content": instructions},
            ]

            # Call LLM
            output = call_llm(
                messages=messages,
                json_mode=True,
            )
            if "LLM Error:" in output or "ChatGPT Error:" in output:
                raise Exception(f"LLM call failed: {output}")

            try:
                data = json.loads(output)
                self.state.final_output = data
                self.report_status(
                    ui_callback, "Final output successfully parsed as JSON."
                )
                await self.publish_event(
                    event_queue, Event(EventType.EXTRACTION_COMPLETE), ui_callback
                )

            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse JSON from LLM response: {json_err}")
                logger.debug(f"Failed LLM response content: {output}")
                self.report_status(
                    ui_callback,
                    f"Failed to parse LLM JSON output: {json_err}",
                    type="error",
                )

                # Store error and raw output in state for debugging
                self.state.final_output = {
                    "error": f"Failed to parse LLM output as JSON: {json_err}",
                    "raw_output": output,
                }

                # Publish complete with error flag for downstream
                await self.publish_event(
                    event_queue, Event(EventType.EXTRACTION_COMPLETE), ui_callback
                )

        except Exception as e:
            logger.error(f"Error during schema extraction LLM call: {e}", exc_info=True)
            self.report_status(
                ui_callback, f"Schema extraction failed: {e}", type="error"
            )
            self.state.final_output = {"error": f"Schema Extraction Failed: {e}"}

            # Publish complete with error flag for downstream
            await self.publish_event(
                event_queue, Event(EventType.EXTRACTION_COMPLETE), ui_callback
            )
