import asyncio
from tavily import AsyncTavilyClient
from features.multi_agent.utility import filter_searches

from ..base_agent import BaseAgent
from ..config import Configuration
from ..events import Event, EventType


class WebSearchAgent(BaseAgent):
    """
    1.  Listens for QUERIES_GENERATED. When triggered:
    2.  Calls Tavily for each query and stores results in state.search_results.
    3.  Publishes SEARCH_RESULTS_READY.
    """

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.QUERIES_GENERATED:
            self.log(f"Received {event.type.name} event.")
            await self.web_search(event_queue)

    async def web_search(self, event_queue) -> None:
        """
        Performs web searches using the Tavily API.
        """
        self.log("Performing Tavily web search...")
        cfg = Configuration()
        tavily_async_client = AsyncTavilyClient(cfg.TAVILY_API_KEY)

        if not self.state.search_queries:
            self.log("No search queries found; cannot perform web search.")
            return

        # Asynchronous web searches
        tasks = []
        for query in self.state.search_queries:
            tasks.append(tavily_async_client.search(query, **cfg.TAVILY_SEARCH_PARAMS))
        search_results = await asyncio.gather(*tasks)

        unique_results = filter_searches(search_results)  # filter duplicates
        self.state.search_results = unique_results

        self.log("Publishing SEARCH_RESULTS_READY.")
        await event_queue.put(Event(EventType.SEARCH_RESULTS_READY))
