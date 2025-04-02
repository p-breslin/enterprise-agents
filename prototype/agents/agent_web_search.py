import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from tavily import AsyncTavilyClient

from .base_agent import BaseAgent
from scripts.state import OverallState
from scripts.events import Event, EventType
from utilities.helpers import filter_searches, get_api_key

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

    async def handle_event(
        self, event: Event, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.QUERIES_GENERATED:
            # Report event
            self.report_status(
                ui_callback, f"Received {event.type.name}, preparing web search."
            )
            try:
                await self.web_search(event_queue, ui_callback)
            except Exception as e:
                self.report_status(
                    ui_callback, f"Web search failed critically: {e}", type="error"
                )

                # Publish error event to halt pipeline
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"WebSearchAgent failed: {e}"},
                    ),
                    ui_callback,
                )

    async def web_search(
        self, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        """
        Performs web searches using the Tavily API.
        """
        # Report event
        self.report_status(ui_callback, "Performing Tavily web search...")

        # Tavily API key
        tavily_api_key = get_api_key(service="TAVILY")

        # Tavily parameters from config
        tavily_async_client = AsyncTavilyClient(tavily_api_key)
        runtime_settings = self.cfg.get("runtime_settings", {})
        tavily_params = runtime_settings.get("tavily_search_params", {})

        if not self.state.search_queries:
            self.report_status(
                ui_callback, "No search queries found. Skipping search.", type="warning"
            )
            self.state.search_results = []
            await self.publish_event(
                event_queue, Event(EventType.SEARCH_RESULTS_READY), ui_callback
            )
            return

        # Asynchronous web searches
        tasks = []
        query_count = len(self.state.search_queries)
        self.report_status(
            ui_callback, f"Preparing {query_count} Tavily search tasks..."
        )
        for query in self.state.search_queries:
            try:
                tasks.append(tavily_async_client.search(query, **tavily_params))
            except Exception as e:
                self.report_status(
                    ui_callback,
                    f"Error preparing search task for '{query}': {e}",
                    type="error",
                )

        if not tasks:
            self.report_status(
                ui_callback, "No valid search tasks could be prepared.", type="warning"
            )
            self.state.search_results = []
            await self.publish_event(
                event_queue, Event(EventType.SEARCH_RESULTS_READY), ui_callback
            )
            return

        try:
            self.report_status(ui_callback, f"Executing {len(tasks)} search tasks...")
            search_results = await asyncio.gather(*tasks)
            self.report_status(ui_callback, "Tavily searches completed.")
        except Exception as e:
            self.report_status(
                ui_callback,
                f"Error during asyncio.gather for searches: {e}",
                type="error",
            )
            return

        # Process and store results
        self.report_status(ui_callback, "Processing search results...")
        unique_results = filter_searches(search_results)  # filter duplicates
        self.state.search_results = unique_results
        self.report_status(
            ui_callback, f"Stored {len(unique_results)} unique search results."
        )

        await self.publish_event(
            event_queue, Event(EventType.SEARCH_RESULTS_READY), ui_callback
        )
