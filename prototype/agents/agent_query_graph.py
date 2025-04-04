import logging
from typing import Dict, Optional, Callable

from .base_agent import BaseAgent
from scripts.state import OverallState
from scripts.events import Event, EventType
from utilities.graph_db import ArangoDBManager

logger = logging.getLogger(__name__)


class GraphQueryAgent(BaseAgent):
    """
    Attempts to retrieve existing information from the ArangoDB knowledge graph.

    Behaviour:
        1. Listens for START_RESEARCH events.
        2. Queries ArangoDB using the company name.
        3. If relevant data is found: GRAPH_DATA_FOUND event published.
        4. If no data is found: NEED_EXTERNAL_DATA event published.
    """

    def __init__(
        self, name: str, state: OverallState, arangodb_manager: ArangoDBManager
    ):
        super().__init__(name, state)
        self.arangodb_manager = arangodb_manager

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
            Expects START_RESEARCH as the trigger.
        """
        # Initialize progress manager
        self.setup_progress(progress_callback)

        if event.type == EventType.START_RESEARCH:
            self.update_status(
                "Received START_RESEARCH event, querying knowledge graph..."
            )

            try:
                await self.query_knowledge_graph(event_queue)
            except Exception as e:
                self.update_status(f"Graph query failed: {e}", type_="error")
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"GraphQueryAgent failed: {e}"},
                    ),
                )

    async def query_knowledge_graph(self, event_queue) -> None:
        """
        Purpose:
            Performs an AQL query with ArangoDB to look for company info.
        Notes:
            Sends different events depending on whether results were found.
        """

        self.update_status(f"Querying knowledge graph for {self.state.company}")

        if not self.arangodb_manager:
            self.update_status("ArangoDB manager unavailable.", type_="error")
            await self.publish_event(event_queue, Event(EventType.NEED_EXTERNAL_DATA))
            return

        # AQL query to find company by a "name" attribute (hard coded!)
        aql_query = """
            FOR doc IN @@collection
            FILTER doc.`name` == @company_name
            LIMIT 1
            RETURN doc
        """

        # Assuming a "Company" collection (hard coded!)
        bind_vars = {
            "@collection": "Company",
            "company_name": self.state.company,
        }

        try:
            # Execute the AQL
            self.update_status("Executing AQL query...")
            query_results = self.arangodb_manager.execute_aql(aql_query, bind_vars)
            self.update_status(f"AQL query returned {len(query_results)} result(s).")
        except Exception as e:
            self.update_status(f"Graph query execution failed: {e}", type_="error")
            query_results = []

        # Store results from the graph
        if query_results:
            self.state.graph_query_results = query_results
            self.update_status("Relevant data found in knowledge graph.")

            # NOTES: need to decide if this data is "sufficient". For now, assume any result bypasses web search. In future, logic could analyze results vs. required schema/workflow goals!

            await self.publish_event(event_queue, Event(EventType.GRAPH_DATA_FOUND))
        else:
            self.update_status("No relevant data found. Triggering web search.")
            await self.publish_event(event_queue, Event(EventType.NEED_EXTERNAL_DATA))
