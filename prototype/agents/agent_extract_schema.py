import json
import logging
from features.multi_agent.LLM import call_llm

from ..config import Configuration
from ..base_agent import BaseAgent
from ..events import Event, EventType
from ..prompts import EXTRACTION_PROMPT


class ExtractionAgent(BaseAgent):
    """
    1.  Listens for RESEARCH_COMPILED. When triggered:
    2.  Finalizes the JSON extraction.
    3.  Publishes EXTRACTION_COMPLETE.
    """

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.RESEARCH_COMPILED:
            self.log(f"Received {event.type.name} event.")
            await self.extract_schema(event_queue)

    async def extract_schema(self, event_queue) -> None:
        self.log("Extracting notes into JSON schema.")
        cfg = Configuration()

        if not self.state.research:
            self.log("No research notes available; cannot extract.")
            return

        instructions = EXTRACTION_PROMPT.format(
            schema=self.state.output_schema, research=self.state.research
        )

        output = call_llm(
            cfg.OPENAI_API_KEY,
            messages=[{"role": "user", "content": instructions}],
            schema=self.state.output_schema,
        )
        try:
            data = json.loads(output)
            self.state.final_output = data
            self.state.complete = True
            self.log("Final output successfully parsed as JSON.")
        except json.JSONDecodeError:
            self.log("Failed to parse JSON from LLM response.")
            logging.debug("Failed LLM response as JSON: {output}")
            self.state.final_output = {}

        self.log("Publishing EXTRACTION_COMPLETE.")
        await event_queue.put(Event(EventType.EXTRACTION_COMPLETE))
