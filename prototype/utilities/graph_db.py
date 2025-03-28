import logging
from typing import Dict, Any, Optional
from arango import ArangoClient
from arango.database import StandardDatabase
from arango.exceptions import (
    ArangoClientError,
    ArangoServerError,
    CollectionCreateError,
    CollectionListError,
    AQLQueryExecuteError,
    DocumentInsertError,
    DocumentGetError,
)

logger = logging.getLogger(__name__)


class ArangoDBManager:
    """
    Manages interactions with an ArangoDB instance, including connection,
    collection management, AQL execution, and graph operations based on
    entity/relationship configurations.
    """

    def __init__(self, host: str, db_name: str, usr: str, pwd: str):
        """
        Initializes the ArangoDBManager and connects to the database.

        Args:
            host (str): The URL of the ArangoDB host.
            db_name (str): The name of the database to connect to.
            usr (str): The username for database authentication.
            pwd (str): The password for database authentication.

        Raises:
            ConnectionError: If the connection to ArangoDB fails.
        """
        self.db_name = db_name
        self._client: Optional[ArangoClient] = None
        self.db: Optional[StandardDatabase] = None

        try:
            logger.info(f"Connecting to ArangoDB host: {host}, database: '{db_name}'")

            # Connect to client
            self._client = ArangoClient(hosts=host)
            self.db = self._client.db(db_name, username=usr, password=pwd)
            logger.info("Successfully connected to ArangoDB.")

            # Verify connection with a simple query
            self.db.version()
            logger.debug("ArangoDB connection verified.")

        except (ArangoClientError, ArangoServerError, Exception) as e:
            logger.error(f"Failed to connect to ArangoDB at {host}: {e}", exc_info=True)
            raise ConnectionError(f"ArangoDB connection failed: {e}") from e

    def _get_collection_name(self, base_name: str, is_edge: bool = False) -> str:
        """
        Applies naming conventions if defined.
        prefix = RELATIONSHIP_PREFIX if is_edge else ENTITY_PREFIX
        return f"{prefix}{base_name}"
        """
        return base_name  # Using direct names for now

    def ensure_collections(
        self, entity_types: list[Dict], relationship_types: list[Dict]
    ) -> None:
        """
        Ensures that document and edge collections exist in the database
        based on the provided entity and relationship type definitions.

        Args:
            entity_types (list[Dict]): List of entity type definitions (expecting dicts with 'name').
            relationship_types (list[Dict]): List of relationship type definitions (expecting dicts with 'name').
        """
        if not self.db:
            logger.error(
                "Database connection not available. Cannot ensure collections."
            )
            return

        logger.info("Ensuring graph collections exist...")
        try:
            # Ensure document collections (Entities)
            if not isinstance(entity_types, list):
                logger.warning(
                    "entity_types configuration is not a list, skipping document collection check."
                )
            else:
                for entity in entity_types:
                    if isinstance(entity, dict) and "name" in entity:
                        collection_name = self._get_collection_name(
                            entity["name"], is_edge=False
                        )
                        if not self.db.has_collection(collection_name):
                            logger.info(
                                f"Creating document collection: '{collection_name}'"
                            )
                            self.db.create_collection(collection_name)
                        else:
                            logger.debug(
                                f"Document collection '{collection_name}' already exists."
                            )
                    else:
                        logger.warning(
                            f"Invalid item in entity_types: {entity}. Expected dict with 'name'."
                        )

            # Ensure edge collections (Relationships)
            if not isinstance(relationship_types, list):
                logger.warning(
                    "relationship_types configuration is not a list, skipping edge collection check."
                )
            else:
                for rel in relationship_types:
                    if isinstance(rel, dict) and "name" in rel:
                        collection_name = self._get_collection_name(
                            rel["name"], is_edge=True
                        )
                        if not self.db.has_collection(collection_name):
                            logger.info(
                                f"Creating edge collection: '{collection_name}'"
                            )
                            self.db.create_collection(collection_name, edge=True)
                        else:
                            logger.debug(
                                f"Edge collection '{collection_name}' already exists."
                            )
                    else:
                        logger.warning(
                            f"Invalid item in relationship_types: {rel}. Expected dict with 'name'."
                        )

        except (CollectionCreateError, CollectionListError, ArangoServerError) as e:
            logger.error(f"Error ensuring collections: {e}", exc_info=True)
        except Exception as e:
            logger.error(
                f"Unexpected error during ensure_collections: {e}", exc_info=True
            )

        logger.info("Collection check complete.")

    def execute_aql(self, query: str, bind_vars: Optional[Dict] = None) -> list[Dict]:
        """
        Executes an AQL query with optional bind variables.

        Args:
            query (str): The AQL query string.
            bind_vars (Optional[Dict]): Dictionary of bind variables for the query.

        Returns:
            list[Dict]: A list of result documents or values. Returns empty list on error.

        Raises:
            ValueError: If the database connection is not available.
        """
        if not self.db:
            raise ValueError("Database connection not available.")

        logger.debug(f"Executing AQL query: {query} with vars: {bind_vars}")
        try:
            # stream=False for simplicity
            cursor = self.db.aql.execute(query, bind_vars=bind_vars, stream=False)
            results = [doc for doc in cursor]
            logger.debug(f"AQL query returned {len(results)} results.")
            return results
        except AQLQueryExecuteError as e:
            logger.error(
                f"AQL query execution failed: {e.http_exception}", exc_info=True
            )
            logger.error(f"Failed AQL Query: {query}")
            logger.error(f"Bind Variables: {bind_vars}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error executing AQL: {e}", exc_info=True)
            return []

    def find_document(
        self, collection_name: str, filter_dict: Dict[str, Any]
    ) -> Optional[Dict]:
        """
        Finds a single document in a collection based on filter criteria.

        Args:
            collection_name (str): The name of the document collection.
            filter_dict (Dict[str, Any]): Dictionary of field-value pairs to filter by.

        Returns:
            Optional[Dict]: The found document or None if not found or error.
        """
        if not self.db or not self.db.has_collection(collection_name):
            logger.warning(
                f"Collection '{collection_name}' not found or DB unavailable."
            )
            return None

        # Build filter string parts dynamically
        filter_parts = []
        bind_vars = {"@collection": collection_name}
        for i, (key, value) in enumerate(filter_dict.items()):
            bind_key = f"filter_value_{i}"
            # Basic check for valid field names (prevent injection)
            if not key.isalnum() and "_" not in key:
                logger.error(
                    f"Invalid character in filter key '{key}'. Skipping filter."
                )
                continue
            filter_parts.append(f"doc.`{key}` == @{bind_key}")
            bind_vars[bind_key] = value

        if not filter_parts:
            logger.error("No valid filters provided for find_document.")
            return None

        filter_string = " AND ".join(filter_parts)
        query = f"""
            FOR doc IN @@collection
            FILTER {filter_string}
            LIMIT 1
            RETURN doc
        """
        results = self.execute_aql(query, bind_vars=bind_vars)
        return results[0] if results else None

    def insert_document(
        self, collection_name: str, document_data: Dict
    ) -> Optional[Dict]:
        """
        Inserts a new document into the specified collection.

        Args:
            collection_name (str): The name of the document collection.
            document_data (Dict): The data for the new document (user attributes).

        Returns:
            Optional[Dict]: The metadata of the newly inserted document or None if insertion fails.
        """
        if not self.db:
            logger.error("Database unavailable. Cannot insert document.")
            return None

        try:
            collection = self.db.collection(collection_name)

            # return_new=True includes full new doc in metadata result['new']
            meta = collection.insert(document_data, return_new=False, overwrite=False)
            logger.info(
                f"Inserted document into '{collection_name}' with key '{meta['_key']}'"
            )
            # Returns dict like {'_id': '...', '_key': '...', '_rev': '...'}
            return meta

        except (DocumentInsertError, ArangoServerError) as e:
            logger.error(
                f"Failed to insert document into '{collection_name}': {e}",
                exc_info=True,
            )
            logger.debug(f"Failed document data: {document_data}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error inserting document: {e}", exc_info=True)
            return None

    def find_or_create_document(
        self, collection_name: str, filter_dict: Dict[str, Any], document_data: Dict
    ) -> Optional[Dict]:
        """
        Finds a document based on filter criteria. If not found, creates it.

        Args:
            collection_name (str): The name of the document collection.
            filter_dict (Dict[str, Any]): Dictionary of field-value pairs to uniquely identify the document.
            document_data (Dict): The full data for the document if it needs to be created (should include the filter_dict fields/values).

        Returns:
            Optional[Dict]: The found or newly created document (including _id, _key), or None on error.
        """
        found_doc = self.find_document(collection_name, filter_dict)
        if found_doc:
            logger.debug(
                f"Found existing document in '{collection_name}' with key '{found_doc['_key']}'."
            )
            return found_doc
        else:
            logger.debug(
                f"Document not found with filter {filter_dict} in '{collection_name}'. Creating..."
            )
            insert_meta = self.insert_document(collection_name, document_data)
            if insert_meta:
                # Fetch the newly created document to return the full object
                try:
                    new_doc = self.db.collection(collection_name).get(
                        insert_meta["_key"]
                    )
                    return new_doc
                except (DocumentGetError, ArangoServerError) as e:
                    logger.error(
                        f"Failed to retrieve newly inserted document '{insert_meta['_key']}': {e}"
                    )
                    return None
            else:
                return None

    def find_or_create_edge(
        self,
        edge_collection_name: str,
        from_doc_id: str,
        to_doc_id: str,
        edge_data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Finds an edge between two documents. If not found, creates it.
        Prevents duplicate edges between the same two nodes in the same direction.

        Args:
            edge_collection_name (str): The name of the edge collection.
            from_doc_id (str): The '_id' of the source document.
            to_doc_id (str): The '_id' of the target document.
            edge_data (Optional[Dict]): Optional attributes for the edge.

        Returns:
            Optional[Dict]: The found or newly created edge document (including _id, _key), or None on error.
        """
        if not self.db or not self.db.has_collection(edge_collection_name):
            logger.warning(
                f"Edge collection '{edge_collection_name}' not found or DB unavailable."
            )
            return None

        # 1. Check if edge already exists
        query = """
            FOR edge IN @@collection
            FILTER edge._from == @from_id AND edge._to == @to_id
            LIMIT 1
            RETURN edge
        """
        bind_vars = {
            "@collection": edge_collection_name,
            "from_id": from_doc_id,
            "to_id": to_doc_id,
        }
        existing_edges = self.execute_aql(query, bind_vars)

        if existing_edges:
            logger.debug(
                f"Edge from '{from_doc_id}' to '{to_doc_id}' already exists in '{edge_collection_name}'."
            )
            return existing_edges[0]
        else:
            # 2. Create edge if it doesn't exist
            logger.debug(
                f"Creating edge from '{from_doc_id}' to '{to_doc_id}' in '{edge_collection_name}'."
            )
            try:
                edge_collection = self.db.collection(edge_collection_name)
                edge_doc = {"_from": from_doc_id, "_to": to_doc_id}
                if edge_data:
                    edge_doc.update(edge_data)

                # return_new=True to get full edge
                meta = edge_collection.insert(edge_doc, return_new=True)
                logger.info(
                    f"Created edge in '{edge_collection_name}' with key '{meta['_key']}'"
                )
                return meta.get("new")  # Return the full new edge document
            except ArangoServerError as e:
                logger.error(
                    f"Failed to create edge in '{edge_collection_name}': {e}",
                    exc_info=True,
                )
                logger.debug(
                    f"Failed edge data: from={from_doc_id}, to={to_doc_id}, data={edge_data}"
                )
                return None
            except Exception as e:
                logger.error(f"Unexpected error creating edge: {e}", exc_info=True)
                return None


# Test
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s - %(message)s",
    )

    from scripts.secrets import Secrets

    secrets = Secrets()

    try:
        # Initialize manager
        db_manager = ArangoDBManager(
            host=secrets.ARANGO_HOST,
            db_name=secrets.ARANGO_DB,
            usr=secrets.ARANGO_USR,
            pwd=secrets.ARANGO_PWD,
        )

        # Entity/relationship definitions (replace with loaded config later)
        mock_entities = [
            {"name": "Company", "attributes": "..."},
            {"name": "Product", "attributes": "..."},
        ]
        mock_relationships = [
            {"name": "develops", "source": "Company", "target": "Product"}
        ]

        # Ensure collections
        db_manager.ensure_collections(mock_entities, mock_relationships)

        # Example operations
        logger.info("\n--- Testing Graph Operations ---")

        # Find or create company
        company_data = {"name": "TestCompany", "industry": "Technology"}
        company_doc = db_manager.find_or_create_document(
            "Company", {"name": "TestCompany"}, company_data
        )
        if company_doc:
            logger.info(f"Company Doc: {company_doc}")
            company_id = company_doc["_id"]

            # Find or create product
            product_data = {"name": "TestProduct", "version": "2.0"}
            product_doc = db_manager.find_or_create_document(
                "Product", {"name": "TestProduct"}, product_data
            )
            if product_doc:
                logger.info(f"Product Doc: {product_doc}")
                product_id = product_doc["_id"]

                # Find or create edge
                edge_data = {"year_developed": 2025}
                edge_doc = db_manager.find_or_create_edge(
                    "develops", company_id, product_id, edge_data
                )
                if edge_doc:
                    logger.info(f"Develops Edge: {edge_doc}")

                # Try creating the same edge again (should find existing)
                edge_doc_again = db_manager.find_or_create_edge(
                    "develops", company_id, product_id, edge_data
                )
                if edge_doc_again:
                    logger.info(
                        f"Develops Edge (Second Attempt - Found): {edge_doc_again}"
                    )

        # Example AQL query
        logger.info("\n--- Testing AQL Execution ---")
        query = "FOR c IN Company FILTER c.name == @name RETURN c"
        bind_vars = {"name": "TestCompany"}
        results = db_manager.execute_aql(query, bind_vars)
        logger.info(f"AQL Query Results: {results}")

    except ConnectionError as e:
        logger.error(f"Could not connect to ArangoDB: {e}")
    except Exception as e:
        logger.error(f"An error occurred during demonstration: {e}", exc_info=True)
