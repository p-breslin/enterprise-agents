import logging
from typing import Dict, List, Any, Optional, Callable

from .base_agent import BaseAgent
from scripts.events import Event, EventType
from scripts.state import OverallState
from utilities.graph_db import ArangoDBManager
from utilities.helpers import normalize_unique_items

logger = logging.getLogger(__name__)

# Define mappings from schema keys to graph collection names (could load from config later). These should match the 'name' field in entity_types.yaml and relationship_types.yaml
ENTITY_COLLECTION_MAP = {
    "company": "Company",
    "product": "Product",
    "competitor": "Competitor",
    "region": "Region",
}
RELATIONSHIP_COLLECTION_MAP = {
    "develops": "develops",  # Company -> Product
    "competes_with": "competes_with",  # Company -> Competitor
    "operates_in": "operates_in",  # Company -> Region
}


class GraphUpdateAgent(BaseAgent):
    """
    Updates the ArangoDB knowledge graph based on structured data.

    Behavior:
        1. Listens for EXTRACTION_COMPLETE.
        2. Parses final_output and creates graph documents and relationships.
        3. Publishes GRAPH_UPDATE_COMPLETE.

    In database operations, "upsert" is a combination of "update" and "insert".
    """

    def __init__(
        self,
        name: str,
        state: OverallState,
        config: Dict[str, Any],
        arangodb_manager: ArangoDBManager,
    ):
        super().__init__(name, state)
        self.config = config
        self.arangodb_manager = arangodb_manager
        self.entity_types = self.config.get("entity_types", {})
        self.relationship_types = self.config.get("relationship_types", {})

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
            Expects EXTRACTION_COMPLETE as the trigger.
        """
        # Initialize progress manager
        self.setup_progress(progress_callback)

        if event.type == EventType.EXTRACTION_COMPLETE:
            self.update_status(
                "Received EXTRACTION_COMPLETE event, updating knowledge graph..."
            )

            try:
                await self.update_graph(event_queue)
            except Exception as e:
                self.update_status(f"Graph update failed: {e}", type_="error")
                self.state.complete = False
                await self.publish_event(
                    event_queue,
                    Event(
                        EventType.ERROR_OCCURRED,
                        payload={"error": f"GraphUpdateAgent failed: {e}"},
                    ),
                )

    async def update_graph(self, event_queue) -> None:
        """
        Purpose:
            Reads structured output and updates graph with company, products, competitors, and regions.
        Notes:
            Updates shared state and emits .
        """
        if not self.arangodb_manager:
            self.update_status("ArangoDB manager unavailable.", type_="error")
            raise ConnectionError("No ArangoDBManager.")

        data = self.state.final_output
        if not isinstance(data, dict) or data.get("error"):
            msg = data.get("error", "Missing or invalid extracted data.")
            self.update_status(f"Skipping graph update: {msg}", type_="warning")
            self.state.complete = False
            await self.publish_event(
                event_queue, Event(EventType.GRAPH_UPDATE_COMPLETE)
            )
            return

        try:
            self.update_status("Starting graph update...")
            company = await self._upsert_company(data)
            if not company:
                raise RuntimeError("Company entity creation failed.")

            # Process product information
            await self._upsert_entities(
                entity_key="products",
                name_field="product_name",
                desc_field="product_description",
                entity_type="product",
                relationship="develops",
                company_doc=company,
            )

            # Process competitor information
            await self._upsert_entities(
                entity_key="competitors",
                name_field="competitor_name",
                desc_field=None,
                entity_type="competitor",
                relationship="competes_with",
                company_doc=company,
            )

            # Process region information
            await self._upsert_regions(data.get("operating_regions", []), company)

            # Mark state as complete if all successful
            self.state.complete = True
            self.update_status("Graph update completed successfully.")

        except Exception as e:
            logger.error("Graph update failed", exc_info=True)
            self.update_status(f"Graph update error: {e}", type_="error")
            self.state.complete = False

        await self.publish_event(event_queue, Event(EventType.GRAPH_UPDATE_COMPLETE))

    async def _upsert_company(self, data: Dict) -> Optional[Dict]:
        """
        Purpose:
            Creates or finds the Company node.
        """
        name = data.get("company_name")
        if not name:
            self.update_status("No company_name found.", type_="warning")
            return None  # Cannot proceed without company name

        # Prepare document data - only include fields present in the input data
        self.update_status(f"Creating/finding Company node: {name}")
        doc = {"name": name, "description": data.get("company_description", "")}

        # Find or create the company document
        return self.arangodb_manager.find_or_create_document(
            collection_name=ENTITY_COLLECTION_MAP["company"],
            filter_dict={"name": name},
            document_data=doc,
        )

    async def _upsert_entities(
        self,
        entity_key: str,
        name_field: str,
        desc_field: Optional[str],
        entity_type: str,
        relationship: str,
        company_doc: Dict,
    ) -> list[Dict]:
        """
        Purpose:
            Generic handler for upserting entitiy nodes (competitors and products for now) and linking them to the company. Returns the successfully processed documents.

        Params:
            entity_key: The key in final_output that holds the entity list.
            name_field: The field name inside each item used as the unique name.
            desc_field: Optional field name used for descriptions.
            entity_type: The entity type key for looking up the collection name.
            relationship: The relationship type used to link to the company.
            company_doc: The ArangoDB company document (must include _id).
        """
        # List of entities
        items = self.state.final_output.get(entity_key, [])
        if not isinstance(items, list):
            self.update_status(f"Invalid format for '{entity_key}'", type_="warning")
            return

        # Remove any duplicates
        items = normalize_unique_items(items, key=name_field)

        # Collection and edge types to use for this entity and relationship
        collection = ENTITY_COLLECTION_MAP.get(entity_type)
        edge_collection = RELATIONSHIP_COLLECTION_MAP.get(relationship)
        company_id = company_doc.get("_id")
        self.update_status(f"Processing {len(items)} {entity_key}...")

        # Skipping any invalid entity formats
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get(name_field)
            if not name:
                continue

            # Adding the description (preparing the document structure)
            doc = {"name": name}
            if desc_field and item.get(desc_field):
                doc["description"] = item[desc_field]

            # Call ArangoDB to create (or retrieve) the doc node for the entity
            result = self.arangodb_manager.find_or_create_document(
                collection_name=collection,
                filter_dict={"name": name},
                document_data=doc,
            )

            # Create 'develops' relationship: Company -> Product
            if result and result.get("_id"):
                self.arangodb_manager.find_or_create_edge(
                    edge_collection_name=edge_collection,
                    from_doc_id=company_id,
                    to_doc_id=result["_id"],
                )
                self.update_status(
                    f"Linked {entity_key[:-1]} '{name}'", type_="agent_log"
                )
            else:
                self.update_status(
                    f"Failed to process {entity_key[:-1]} '{name}'", type_="warning"
                )

    async def _upsert_regions(self, regions: List[str], company_doc: Dict) -> None:
        """
        Purpose:
            Upserts region entities and connects them to the company in the graph.

        Notes:
            Each region is added as a document (if not already present) and connected to the company via an operates_in relationship edge.
        """
        if not isinstance(regions, list):
            self.update_status("Invalid 'operating_regions' format.", type_="warning")
            return

        # Remove any duplicates
        regions = normalize_unique_items(regions)

        # Collection and edge types to use for this entity and relationship
        collection = ENTITY_COLLECTION_MAP.get("region")
        edge_collection = RELATIONSHIP_COLLECTION_MAP.get("operates_in")
        company_id = company_doc.get("_id")
        self.update_status(f"Processing {len(regions)} regions...")

        # Skipping any invalid entity formats
        for region in regions:
            if not isinstance(region, str) or not region.strip():
                continue

            # Build the data payload for the region entity
            region = region.strip()
            doc = {"name": region}

            # Find region in the graph by name or create it
            result = self.arangodb_manager.find_or_create_document(
                collection_name=collection,
                filter_dict={"name": region},
                document_data=doc,
            )

            # Create 'operates_in' relationship: Company -> Region
            if result and result.get("_id"):
                self.arangodb_manager.find_or_create_edge(
                    edge_collection_name=edge_collection,
                    from_doc_id=company_id,
                    to_doc_id=result["_id"],
                )
                self.update_status(f"Linked region '{region}'", type_="agent_log")
            else:
                self.update_status(
                    f"Failed to process region '{region}'", type_="warning"
                )
