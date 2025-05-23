import json
import logging
from agno.tools import tool
from typing import Dict, Any, Optional
from integrations.arango_client import arango_connect
from arango.exceptions import AQLQueryExecuteError, ArangoServerError

log = logging.getLogger(__name__)


@tool
def arango_upsert(
    collection_name: str,
    search_document: Dict[str, Any],
    insert_document: Dict[str, Any],
    update_document: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Performs an ArangoDB UPSERT operation: updates a document if found based on search criteria, otherwise inserts a new document.

    This tool constructs and executes a safe UPSERT AQL query using bind variables.

    Args:
        collection_name (str): The name of the collection to perform the upsert in. REQUIRED.

        search_document (Dict[str, Any]): A dictionary defining the filter criteria to find an existing document (e.g., {'_key': 'mykey'} or {'email': 'user@example.com'}). REQUIRED.

        insert_document (Dict[str, Any]): The full document object to insert if no document matches the `search_document`. REQUIRED. Ensure this includes the fields used in `search_document` if you want them present on insert (e.g., include `_key`).

        update_document (Dict[str, Any]): A dictionary containing the fields and new values to apply if a document *is* found by `search_document`. This performs a partial update on the found document. REQUIRED.

        options (Optional[Dict[str, Any]]): Additional ArangoDB options for the UPSERT operation (e.g., {'waitForSync': True, 'keepNull': False}). Consult ArangoDB documentation for available options. OPTIONAL.

    Returns:
        str: A A JSON string representation of a dictionary containing the execution status and result.
            - On Success:
                {
                    "status": "success",
                    "result": Dict | None
                }
            - On Failure:
                {
                    "status": "error",
                    "error": "A brief error description (e.g., 'AQL Execution Error', 'Collection Not Found')",
                    "details": "Specific error message from the database or system.",
                    "status_code": Optional HTTP status code if available.
                }
    """
    log.info(f"Tool 'arango_upsert' called for collection '{collection_name}'")
    log.debug(
        f"Search: {search_document}, Insert: {insert_document}, Update: {update_document}, Options: {options}"
    )

    # --- Construct the AQL Query ---
    aql_parts = [
        "UPSERT @search",
        "INSERT @insert",
        "UPDATE @update",
        "IN @@collection",  # Use @@ for collection bind variable
    ]

    bind_vars = {
        "search": search_document,
        "insert": insert_document,
        "update": update_document,
        "@collection": collection_name,  # Single @ for collection name in bind_vars dict
    }

    if options:
        # Ensure options is a dictionary before binding
        if isinstance(options, dict):
            aql_parts.append("OPTIONS @options")
            bind_vars["options"] = options
            log.debug(f"Applying UPSERT options: {options}")
        else:
            log.warning(
                f"Ignoring invalid 'options' parameter (must be a dictionary): {options}"
            )

    result_document = None
    aql_parts.append("RETURN NEW")

    query = "\n".join(aql_parts)
    log.debug(f"Executing AQL: {query}")
    log.debug(
        f"With Bind Vars: {bind_vars}"
    )  # Be cautious logging sensitive data in production

    # --- Execute the Query ---
    try:
        db = arango_connect()
        cursor = db.aql.execute(query, bind_vars=bind_vars, stream=False)

        # UPSERT...RETURN NEW returns the single affected document
        result_list = [doc for doc in cursor]
        if result_list:
            result_document = result_list[0]
            log.info(
                f"Upsert successful, returned document with key '{result_document.get('_key')}'"
            )
        else:
            # Should not happen with RETURN NEW on success, but handle defensively
            log.warning("Upsert executed but RETURN NEW yielded no document.")

        return json.dumps({"status": "success"})

    # Error handling
    except AQLQueryExecuteError as e:
        log.error("AQL Execution Error during UPSERT", exc_info=True)
        return json.dumps(
            {
                "status": "error",
                "error": "AQL Execution Error",
                "details": str(e),
            }
        )
    except ArangoServerError as e:
        # Catch other potential server-side issues
        http_exception = getattr(e, "http_exception", None)
        details = (
            http_exception.response.text
            if http_exception and hasattr(http_exception, "response")
            else str(e)
        )
        status_code = (
            http_exception.response.status_code
            if http_exception and hasattr(http_exception, "response")
            else None
        )
        error_msg = "ArangoDB Server Error during UPSERT"
        log.error(f"{error_msg}: {details}")
        return json.dumps(
            {
                "status": "error",
                "error": "ArangoDB Server Error",
                "details": details,
                "status_code": status_code,
            }
        )
    except ConnectionError as e:  # Catch connection errors from db connection
        error_msg = f"Database connection failed: {e}"
        log.error(error_msg)
        return json.dumps(
            {"status": "error", "error": "Connection Error", "details": str(e)}
        )
    except Exception as e:
        # Catch-all for unexpected errors
        error_msg = f"An unexpected error occurred in arango_upsert: {e}"
        log.exception(error_msg)  # Include traceback
        return json.dumps(
            {"status": "error", "error": "Unexpected Tool Error", "details": str(e)}
        )
