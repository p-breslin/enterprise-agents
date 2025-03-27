from features.multi_agent.LLM import call_llm

from ..config import Configuration
from ..base_agent import BaseAgent
from ..events import Event, EventType
from ..prompts import RESEARCH_PROMPT
from ..utility import format_results


class ResearchAgent(BaseAgent):
    """
    1.  Listens for either DB_CHECK_DONE (if DB had data) or SEARCH_RESULTS_READY (if we had to do a web search).
    2.  Compiles research notes and publishes RESEARCH_COMPILED.
    """

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type in [EventType.DB_CHECK_DONE, EventType.SEARCH_RESULTS_READY]:
            self.log(f"Received {event.type.name} event.")
            await self.compile_research(event_queue)

    async def compile_research(self, event_queue) -> None:
        self.log("Compiling research notes.")
        cfg = Configuration()

        context_str = format_results(self.state.search_results)
        instructions = RESEARCH_PROMPT.format(
            company=self.state.company,
            schema=self.state.output_schema,
            context=context_str,
        )

        research_notes = call_llm(
            cfg.OPENAI_API_KEY, messages=[{"role": "user", "content": instructions}]
        )
        self.state.research.append(research_notes)
        self.log("Reesearch notes completed.")

        self.log("Publishing RESEARCH_COMPILED.")
        await event_queue.put(Event(EventType.RESEARCH_COMPILED))
