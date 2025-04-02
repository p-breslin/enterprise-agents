import logging
from typing import Dict, Any, Optional

from .base_agent import BaseAgent
from scripts.events import Event, EventType
from scripts.state import OverallState
from utilities.graph_db import ArangoDBManager

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
    1. Listens for EXTRACTION_COMPLETE.
    2. Parses the extracted JSON data from state.final_output.
    3. Uses ArangoDBManager to create/update corresponding nodes (documents) and
       edges in the knowledge graph based on entity/relationship type definitions.
    4. Publishes GRAPH_UPDATE_COMPLETE on success.
    """

    def __init__(
        self,
        name: str,
        state: OverallState,
        config: Dict[str, Any],  # Main config for entity/relationship details
        arangodb_manager: ArangoDBManager,
    ):
        super().__init__(name, state)
        self.config = config
        self.arangodb_manager = arangodb_manager
        self.entity_types = self.config.get("entity_types", {})
        self.relationship_types = self.config.get("relationship_types", {})

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Handles EXTRACTION_COMPLETE event.
        """
        if event.type == EventType.EXTRACTION_COMPLETE:
            self.log(f"Received {event.type.name} event. Updating knowledge graph.")
            await self.update_graph(event_queue)

    async def update_graph(self, event_queue) -> None:
        """
        Parses extracted data and updates the ArangoDB graph.
        """
        if not self.arangodb_manager:
            logger.error("ArangoDB manager is not available. Cannot update graph.")
            await event_queue.put(
                Event(
                    EventType.ERROR_OCCURRED,
                    payload={"error": "ArangoDB unavailable for graph update"},
                )
            )
            return

        extracted_data = self.state.final_output
        if (
            not extracted_data
            or not isinstance(extracted_data, dict)
            or extracted_data.get("error")
        ):
            logger.warning(
                f"No valid extracted data found in state.final_output ({extracted_data}). Skipping graph update."
            )
            if isinstance(extracted_data, dict) and extracted_data.get("error"):
                logger.error("Graph update skipped due to previous extraction error.")
            else:
                logger.warning(
                    "Graph update skipped due to missing or invalid extraction data."
                )
            return

        try:
            self.log("Starting graph update process...")
            company_doc = await self._process_company(extracted_data)
            if not company_doc:
                raise ValueError("Failed to process main company entity.")

            # process product_docs, competitor_docs, region_docs
            await self._process_products(extracted_data, company_doc)
            await self._process_competitors(extracted_data, company_doc)
            await self._process_regions(extracted_data, company_doc)

            # –– Mark state as complete and publish success ––
            self.state.complete = True
            self.log("Graph update process finished successfully.")
            await event_queue.put(Event(EventType.GRAPH_UPDATE_COMPLETE))

        except Exception as e:
            logger.error(f"Error occurred during graph update: {e}", exc_info=True)
            self.state.complete = False
            await event_queue.put(
                Event(
                    EventType.ERROR_OCCURRED,
                    payload={"error": f"Graph update failed: {e}"},
                )
            )

    async def _process_company(self, data: Dict) -> Optional[Dict]:
        """
        Processes the main company entity.
        """
        company_name = data.get("company_name")
        if not company_name:
            logger.warning("No 'company_name' found in extracted data.")
            return None  # Cannot proceed without company name

        collection_name = ENTITY_COLLECTION_MAP.get("company")
        if not collection_name:
            logger.error("Mapping for 'company' entity collection not found.")
            return None

        # Prepare document data - only include fields present in the input data
        company_data = {"name": company_name}
        if "company_description" in data:
            company_data["description"] = data["company_description"]

        # Find or create the company document
        company_doc = self.arangodb_manager.find_or_create_document(
            collection_name=collection_name,
            filter_dict={"name": company_name},
            document_data=company_data,
        )
        if company_doc:
            self.log(
                f"Processed company: {company_name} (ID: {company_doc.get('_id')})"
            )
        else:
            logger.error(
                f"Failed to find or create company document for: {company_name}"
            )

        return company_doc  # Return the ArangoDB document (including _id)

    async def _process_products(self, data: Dict, company_doc: Dict) -> list[Dict]:
        """
        Processes products and links them to the company.
        """
        processed_products = []
        product_list = data.get("products", [])
        if not isinstance(product_list, list):
            logger.warning("'products' field is not a list in extracted data.")
            return []

        company_id = company_doc.get("_id")
        if not company_id:
            return []  # Should not happen if company_doc is valid

        prod_collection = ENTITY_COLLECTION_MAP.get("product")
        dev_collection = RELATIONSHIP_COLLECTION_MAP.get("develops")

        if not prod_collection or not dev_collection:
            logger.error(
                "Collection mapping missing for 'product' or 'develops'. Cannot process products."
            )
            return []

        for product_item in product_list:
            if not isinstance(product_item, dict):
                continue
            product_name = product_item.get("product_name")
            if not product_name:
                continue

            # Prepare product data
            product_data = {"name": product_name}
            if "product_description" in product_item:
                product_data["description"] = product_item["product_description"]

            # Find or create product document(assuming product name is unique)
            product_doc = self.arangodb_manager.find_or_create_document(
                collection_name=prod_collection,
                filter_dict={"name": product_name},
                document_data=product_data,
            )

            if product_doc and product_doc.get("_id"):
                processed_products.append(product_doc)
                self.log(f"Processed product: {product_name}")

                # Create 'develops' relationship: Company -> Product
                self.arangodb_manager.find_or_create_edge(
                    edge_collection_name=dev_collection,
                    from_doc_id=company_id,
                    to_doc_id=product_doc["_id"],
                )
            else:
                logger.warning(f"Failed to process product: {product_name}")

        return processed_products

    async def _process_competitors(self, data: Dict, company_doc: Dict) -> list[Dict]:
        """
        Processes competitors and links them to the company.
        """
        processed_competitors = []
        competitor_list = data.get("competitors", [])
        if not isinstance(competitor_list, list):
            logger.warning("'competitors' field is not a list in extracted data.")
            return []

        company_id = company_doc.get("_id")
        if not company_id:
            return []

        comp_collection = ENTITY_COLLECTION_MAP.get("competitor")
        competes_collection = RELATIONSHIP_COLLECTION_MAP.get("competes_with")

        if not comp_collection or not competes_collection:
            logger.error(
                "Collection mapping missing for 'competitor' or 'competes_with'."
            )
            return []

        for competitor_item in competitor_list:
            if not isinstance(competitor_item, dict):
                continue
            competitor_name = competitor_item.get("competitor_name")
            if not competitor_name:
                continue

            # Assume dedicated 'Competitor' collection for competitors
            competitor_data = {"name": competitor_name}

            # Find or create competitor document
            competitor_doc = self.arangodb_manager.find_or_create_document(
                collection_name=comp_collection,
                filter_dict={"name": competitor_name},
                document_data=competitor_data,
            )

            if competitor_doc and competitor_doc.get("_id"):
                processed_competitors.append(competitor_doc)
                self.log(f"Processed competitor: {competitor_name}")

                # Create 'competes_with' relationship: Company -> Competitor
                # (..or should it be Product -> Competitor ?)
                self.arangodb_manager.find_or_create_edge(
                    edge_collection_name=competes_collection,
                    from_doc_id=company_id,
                    to_doc_id=competitor_doc["_id"],
                )
            else:
                logger.warning(f"Failed to process competitor: {competitor_name}")

        return processed_competitors

    async def _process_regions(self, data: Dict, company_doc: Dict) -> list[Dict]:
        """
        Processes operating regions and links them to the company.
        """
        processed_regions = []
        region_list = data.get("operating_regions", [])
        if not isinstance(region_list, list):
            logger.warning("'operating_regions' field is not a list in extracted data.")
            return []

        company_id = company_doc.get("_id")
        if not company_id:
            return []

        reg_collection = ENTITY_COLLECTION_MAP.get("region")
        operates_collection = RELATIONSHIP_COLLECTION_MAP.get("operates_in")

        if not reg_collection or not operates_collection:
            logger.error("Collection mapping missing for 'region' or 'operates_in'.")
            return []

        for region_name in region_list:
            if not isinstance(region_name, str) or not region_name.strip():
                continue
            region_name = region_name.strip()

            # Find or create region document
            region_data = {"name": region_name}  # assuming region only has name
            region_doc = self.arangodb_manager.find_or_create_document(
                collection_name=reg_collection,
                filter_dict={"name": region_name},
                document_data=region_data,
            )

            if region_doc and region_doc.get("_id"):
                processed_regions.append(region_doc)
                self.log(f"Processed region: {region_name}")

                # Create 'operates_in' relationship: Company -> Region
                self.arangodb_manager.find_or_create_edge(
                    edge_collection_name=operates_collection,
                    from_doc_id=company_id,
                    to_doc_id=region_doc["_id"],
                )
            else:
                logger.warning(f"Failed to process region: {region_name}")

        return processed_regions
