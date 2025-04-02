import logging
from .base_agent import BaseAgent
from scripts.state import OverallState
from scripts.events import Event, EventType
from utilities.graph_db import ArangoDBManager
from typing import Dict, Any, Optional, Callable


logger = logging.getLogger(__name__)


class GraphQueryAgent(BaseAgent):
    """
    1. Listens for START_RESEARCH.
    2. Queries the ArangoDB graph for existing information about the company.
    3. If relevant structured data found; stores in state.graph_query_results and publishes GRAPH_DATA_FOUND.
    4. If no/insufficient data is found, publishes NEED_EXTERNAL_DATA.
    """

    def __init__(
        self, name: str, state: OverallState, arangodb_manager: ArangoDBManager
    ):
        """
        Args:
            name (str): The name of the agent.
            state (OverallState): The shared state object.
            arangodb_manager (ArangoDBManager): The manager instance for ArangoDB interaction.
        """
        super().__init__(name, state)
        self.arangodb_manager = arangodb_manager

    async def handle_event(
        self, event: Event, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.START_RESEARCH:
            self.report_status(
                ui_callback, f"Received {event.type.name}, querying knowledge graph..."
            )
            try:
                await self.query_knowledge_graph(event_queue, ui_callback)
            except Exception as e:
                self.report_status(
                    ui_callback, f"Graph query failed critically: {e}", type="error"
                )
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"GraphQueryAgent failed: {e}"},
                    ),
                    ui_callback,
                )

    async def query_knowledge_graph(
        self, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ) -> None:
        """
        Queries the ArangoDB graph for information related to the company.
        """
        self.report_status(
            ui_callback, f"Querying graph for company: {self.state.company}"
        )

        if not self.arangodb_manager:
            self.report_status(
                ui_callback,
                "ArangoDB manager unavailable. Cannot query graph.",
                type="error",
            )

            # Trigger external search as if graph had no data
            await self._publish_need_external_data(event_queue, ui_callback)
            return

        # --- Define AQL Query ---
        # This query aims to find the company node and perhaps directly related info. Assumes a 'Company' collection with a 'name' attribute.
        company_collection = "Company"
        company_name_field = "name"

        # Example AQL: Find company node by name
        aql_query = f"""
            FOR doc IN @@collection
            FILTER doc.`{company_name_field}` == @company_name
            LIMIT 1
            RETURN doc
        """
        bind_vars = {
            "@collection": company_collection,
            "company_name": self.state.company,
        }
        query_results = []  # Default to empty list

        # --- Execute Query ---
        try:
            self.report_status(ui_callback, "Executing AQL query...")
            query_results = self.arangodb_manager.execute_aql(aql_query, bind_vars)
            self.report_status(
                ui_callback, f"AQL query returned {len(query_results)} results."
            )
        except Exception as e:
            # Log detailed error but report generic failure
            logger.error(
                f"An error occurred during graph query execution: {e}", exc_info=True
            )
            self.report_status(
                ui_callback, f"Graph query execution failed: {e}", type="error"
            )
            # For simplicity, treat query execution error same as no data found
            query_results = []

        # --- Process Results ---
        if query_results:
            self.report_status(
                ui_callback,
                f"Found {len(query_results)} item(s) in the knowledge graph.",
            )
            # Store the raw results from the graph query
            self.state.graph_query_results = query_results

            # Need to decide if this data is "sufficient". For now, assume any result bypasses web search. In future, logic could analyze results vs. required schema/workflow goals.

            await self.publish_event(
                event_queue, Event(EventType.GRAPH_DATA_FOUND), ui_callback
            )
        else:
            self.report_status(
                ui_callback, "No relevant data found in the knowledge graph."
            )
            await self._publish_need_external_data(event_queue, ui_callback)

    async def _publish_need_external_data(
        self, event_queue, ui_callback: Optional[Callable[[Dict], None]]
    ):
        """
        Helper to publish the event indicating external data is needed.
        """
        await self.publish_event(
            event_queue, Event(EventType.NEED_EXTERNAL_DATA), ui_callback
        )
