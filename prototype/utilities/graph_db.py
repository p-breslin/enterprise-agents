import logging
from typing import Optional, Dict, Any, List

from arango import ArangoClient
from arango.database import StandardDatabase
from arango.exceptions import (
    CollectionCreateError,
    AQLQueryExecuteError,
    DocumentInsertError,
)

logger = logging.getLogger(__name__)


class ArangoDBManager:
    """
    Wrapper class to manage ArangoDB connections and common operations: collection creation, document and edge upserts, and AQL queries.
    """

    def __init__(self, host: str, db_name: str, usr: str, pwd: str):
        """
        Purpose:
            Establishes a connection to the specified ArangoDB database using provided credentials.
        Notes:
            - Assumes the database already exists.
        """
        self.db_name = db_name
        self._client: Optional[ArangoClient] = None
        self.db: Optional[StandardDatabase] = None

        try:
            self._client = ArangoClient(hosts=host)
            self.db = self._client.db(db_name, username=usr, password=pwd)
            self.db.version()  # verifies connection with a simple query
            logger.info(f"Connected to ArangoDB at {host} (DB: {db_name})")

        except Exception as e:
            logger.error(f"Connection to ArangoDB failed: {e}", exc_info=True)
            raise ConnectionError(f"ArangoDB connection error: {e}") from e

    def ensure_collections(
        self,
        entity_types: List[Dict[str, Any]],
        relationship_types: List[Dict[str, Any]],
    ) -> None:
        """
        Purpose:
            Ensures that all entity + relationship collections exist in the DB.
        Notes:
            - Creates missing document collections for entities.
            - Creates missing edge collections for relationships.
        """
        if not self.db:
            logger.error("Cannot ensure collections (bad DB connection)")
            return

        logger.info("Ensuring graph collections exist...")

        # Ensure document collections exist (Entities / Nodes)
        for entity in entity_types:
            name = entity.get("name")

            # Create the collection if not existing
            if name and not self.db.has_collection(name):
                try:
                    self.db.create_collection(name)
                    logger.info(f"Created entity collection: {name}")
                except CollectionCreateError as e:
                    logger.warning(f"Failed to create entity collection {name}: {e}")

        # Ensure edge collections (Relationships / Edges)
        for rel in relationship_types:
            name = rel.get("name")

            # Create the collection if not existing
            if name and not self.db.has_collection(name):
                try:
                    self.db.create_collection(name, edge=True)
                    logger.info(f"Created relationship collection: {name}")
                except CollectionCreateError as e:
                    logger.warning(
                        f"Failed to create relationship collection {name}: {e}"
                    )

        logger.info("Collection check complete.")

    def find_or_create_document(
        self,
        collection_name: str,
        filter_dict: Dict[str, Any],
        document_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Purpose:
            Retrieves a document matching the filter. If none found, inserts the provided document data.
        Notes:
            - Uses AQL to find the existing document.
            - "Find the first document in the collection called collection_name where all the key-value pairs in filter_dict match".
            - @@collection is Arango syntax for bindable collection names.
            - bind_vars binds values into the query.
            - “cursor” = a stream of results.
        """
        # Execute the AQL query
        try:
            # @@collection = placeholder replaced by the real collection name
            cursor = self.db.aql.execute(
                f"""
                FOR doc IN @@collection
                    FILTER {self._build_filter("doc", filter_dict)}
                    LIMIT 1
                    RETURN doc
                """,
                bind_vars={"@collection": collection_name, **filter_dict},
            )
            doc = next(cursor, None)
            if doc:
                return doc

            # If no match is found; insert the document and return the result
            inserted = self.db.collection(collection_name).insert(
                document_data, overwrite=False
            )
            return inserted

        except (AQLQueryExecuteError, DocumentInsertError) as e:
            logger.error(
                f"Document operation failed ({collection_name}): {e}", exc_info=True
            )
            return None

    def find_or_create_edge(
        self,
        edge_collection_name: str,
        from_doc_id: str,
        to_doc_id: str,
        edge_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Purpose:
            Retrieves an edge between two documents. If not found, inserts a new edge with optional data.

        Notes:
            - (_from) and (_to) IDs are required.
            - “Search for an edge in the edge collection that connects from_doc_id to to_doc_id. Return that edge if it exists”.
            - Used to prevent inserting duplicate edges between two nodes.

        """
        # Default to {} to avoid mutation bugs
        edge_data = edge_data or {}

        # Attempt to find existing edge with AQL query
        try:
            query = """
                FOR edge IN @@edge_collection
                    FILTER edge._from == @from_id AND edge._to == @to_id
                    LIMIT 1
                    RETURN edge
            """
            bind_vars = {
                "@edge_collection": edge_collection_name,
                "from_id": from_doc_id,
                "to_id": to_doc_id,
            }
            cursor = self.db.aql.execute(query, bind_vars=bind_vars)
            edge = next(cursor, None)
            if edge:
                return edge

            # Build the edge payload and inserts it if not found
            edge_payload = {"_from": from_doc_id, "_to": to_doc_id, **edge_data}
            return self.db.collection(edge_collection_name).insert(edge_payload)

        except (AQLQueryExecuteError, DocumentInsertError) as e:
            logger.error(
                f"Edge operation failed ({edge_collection_name}): {e}", exc_info=True
            )
            return None

    def execute_aql(
        self, query: str, bind_vars: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Purpose:
            Executes a raw AQL query with bind variables and returns results as a list (takes query + bind vars and returns list of results).
        Notes:
            - If query fails, logs the error and returns an empty list.
            - Used for graph lookups or custom queries.
        """
        try:
            cursor = self.db.aql.execute(query, bind_vars=bind_vars)
            return list(cursor)
        except AQLQueryExecuteError as e:
            logger.error(f"AQL execution failed: {e}", exc_info=True)
            return []

    @staticmethod
    def _build_filter(var_prefix: str, filters: Dict[str, Any]) -> str:
        """
        Purpose:
            Builds an AQL filter clause from a dict of field-value pairs.
        Notes:
            - Used to dynamically construct WHERE conditions in AQL queries.
            - Example: {name: "Nvidia"} —> "doc.name == @name"
            - “Take a dict of field-value pairs and build a string of filter conditions that checks if each field = the corresponding variable.”

        """
        return " AND ".join([f"{var_prefix}.{f} == @{f}" for f in filters])
