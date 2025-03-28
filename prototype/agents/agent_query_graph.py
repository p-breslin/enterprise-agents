import logging
from .base_agent import BaseAgent
from scripts.state import OverallState
from scripts.events import Event, EventType
from utilities.graph_db import ArangoDBManager

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

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.START_RESEARCH:
            self.log(f"Received {event.type.name} event. Querying knowledge graph.")
            await self.query_knowledge_graph(event_queue)

    async def query_knowledge_graph(self, event_queue) -> None:
        """
        Queries the ArangoDB graph for information related to the company.
        """
        self.log(f"Querying graph for company: {self.state.company}")

        if not self.arangodb_manager:
            logger.error("ArangoDB manager is not available. Cannot query graph.")
            # Trigger external search as if graph had no data
            await self._publish_need_external_data(event_queue)
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

        # --- Execute Query ---
        try:
            query_results = self.arangodb_manager.execute_aql(aql_query, bind_vars)
        except Exception as e:
            logger.error(
                f"An error occurred during graph query execution: {e}", exc_info=True
            )
            # Treat query execution error same as no data found for simplicity
            query_results = []

        # --- Process Results ---
        if query_results:
            self.log(
                f"Found {len(query_results)} relevant item(s) in the knowledge graph."
            )
            # Store the raw results from the graph query
            self.state.graph_query_results = query_results

            # Decide if this data is "sufficient". For now, assume any result bypasses web search. In future, logic could analyze results vs. required schema/workflow goals.

            self.log("Publishing GRAPH_DATA_FOUND.")
            await event_queue.put(Event(EventType.GRAPH_DATA_FOUND))
        else:
            self.log("No relevant data found in the knowledge graph.")
            await self._publish_need_external_data(event_queue)

    async def _publish_need_external_data(self, event_queue):
        """
        Helper to publish the event indicating external data is needed.
        """
        self.log("Publishing NEED_EXTERNAL_DATA.")
        await event_queue.put(Event(EventType.NEED_EXTERNAL_DATA))
