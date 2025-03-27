import re
import json
from features.multi_agent.LLM import call_llm

from ..config import Configuration
from ..base_agent import BaseAgent
from ..events import Event, EventType
from ..prompts import QUERY_LIST_PROMPT, QUERY_GENERATOR_PROMPT


class QueryGenerationAgent(BaseAgent):
    """
    1.  Listens for NEED_QUERIES. When triggered:
    2.  Generates queries via the LLM and stores them in state.search_queries.
    3.  Publishes QUERIES_GENERATED.
    """

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.NEED_QUERIES:
            self.log(f"Received {event.type.name} event.")
            await self.generate_queries(event_queue)

    async def generate_queries(self, event_queue) -> None:
        """
        Generates search queries using LLM.
        """
        self.log(f"Generating search queries for {self.state.company}.")
        cfg = Configuration()

        instructions = QUERY_GENERATOR_PROMPT.format(
            company=self.state.company,
            schema=json.dumps(self.state.output_schema, indent=2),
            N_searches=cfg.N_searches,
        )
        messages = [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": QUERY_LIST_PROMPT.format(N_searches=cfg.N_searches),
            },
        ]
        output = call_llm(cfg.OPENAI_API_KEY, messages)

        search_queries = re.findall(r'"\s*(.*?)\s*"', output)  # clean if needed
        self.state.search_queries = search_queries
        self.log(f"Generated search queries: {self.state.search_queries}")

        self.log("Publishing QUERIES_GENERATED.")
        await event_queue.put(Event(EventType.QUERIES_GENERATED))
