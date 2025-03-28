import asyncio
import logging
from typing import Dict, Any
from tavily import AsyncTavilyClient

from .base_agent import BaseAgent
from scripts.secrets import Secrets
from scripts.state import OverallState
from scripts.events import Event, EventType
from utilities.helpers import filter_searches

logger = logging.getLogger(__name__)


class WebSearchAgent(BaseAgent):
    """
    1.  Listens for QUERIES_GENERATED. When triggered:
    2.  Calls Tavily for each query and stores results in state.search_results.
    3.  Publishes SEARCH_RESULTS_READY.
    """

    def __init__(self, name: str, state: OverallState, config: Dict[str, Any]):
        super().__init__(name, state)
        self.cfg = config

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

        # Tavily API key
        try:
            api_keys = Secrets()
            tavily_api_key = api_keys.TAVILY_API_KEY
            if not tavily_api_key:
                raise ValueError("TAVILY_API_KEY is not set in environment variables.")
        except Exception as e:
            logger.error(f"Failed to get Tavily API Key: {e}", exc_info=True)
            return

        # Tavily parameters from config
        tavily_async_client = AsyncTavilyClient(tavily_api_key)
        runtime_settings = self.cfg.get("runtime_settings", {})
        tavily_params = runtime_settings.get("tavily_search_params", {})

        if not self.state.search_queries:
            self.log("No search queries found; cannot perform web search.")
            self.state.search_results = []
            await event_queue.put(Event(EventType.SEARCH_RESULTS_READY))
            return

        # Asynchronous web searches
        tasks = []
        for query in self.state.search_queries:
            try:
                tasks.append(tavily_async_client.search(query, **tavily_params))
            except Exception as e:
                logger.error(
                    f"Error preparing Tavily search task for query '{query}': {e}"
                )

        if not tasks:
            logger.warning("No valid search tasks could be prepared.")
            self.state.search_results = []
            await event_queue.put(Event(EventType.SEARCH_RESULTS_READY))
            return

        try:
            search_results = await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(
                f"Error occurred during asyncio.gather for Tavily searches: {e}"
            )
            return

        # Process and store results
        unique_results = filter_searches(search_results)  # filter duplicates
        self.state.search_results = unique_results

        self.log("Publishing SEARCH_RESULTS_READY.")
        await event_queue.put(Event(EventType.SEARCH_RESULTS_READY))
