import os
import logging
from typing import Optional
from dotenv import load_dotenv
from arango import ArangoClient
from arango.database import StandardDatabase

load_dotenv()
log = logging.getLogger(__name__)


# --- Module-level cache for ArangoDB connection ---
_cached_arango_conn: Optional[StandardDatabase] = None


def arango_connect(db_name="ARANGO_DB_JIRA") -> Optional[StandardDatabase]:
    """
    Returns a cached ArangoDB database connection (initializes it on first call)
    """
    global _cached_arango_conn

    # Return cached connection if already initialized
    if _cached_arango_conn is not None:
        log.debug("Returning cached ArangoDB connection.")
        return _cached_arango_conn

    # Initialize connection if not cached
    log.info("Initializing new ArangoDB connection...")
    try:
        DB = os.getenv(db_name)
        HST = os.getenv("ARANGO_HOST")
        USR = os.getenv("ARANGO_USERNAME")
        PWD = os.getenv("ARANGO_PASSWORD")

        # Connect to ArangoDB server
        client = ArangoClient(hosts=HST)
        conn = client.db(DB, username=USR, password=PWD)

        # Verify connection
        conn.version()
        log.info(f"Successfully connected to ArangoDB: {HST}, DB: {DB}")
        _cached_arango_conn = conn  # Cache the connection
        return _cached_arango_conn

    except Exception as e:
        log.error(f"Failed to connect to ArangoDB server: {e}")
        _cached_arango_conn = None
        return None


def reset_arango_connection_cache():
    """
    Resets the cached ArangoDB connection.
    """
    global _cached_arango_conn
    log.debug("Resetting cached ArangoDB connection.")
    _cached_arango_conn = None
