import os
import logging
from dotenv import load_dotenv
from arango import ArangoClient
from utils.helpers import load_config
from utils.logging_setup import setup_logging


load_dotenv()
setup_logging()
log = logging.getLogger(__name__)

runtime = load_config("runtime")
database_name = "ARANGO_DB_ORG"


# First deleting the database (starting fresh)
try:
    # Connect to ArangoDB server
    client = ArangoClient(hosts=os.getenv("ARANGO_HOST"))

    try:
        # Authenticate with root user (required to manage databases)
        sys_db = client.db(
            "_system", username="root", password=os.getenv("ARANGO_PASSWORD")
        )

        db_name = os.getenv(database_name)

        # Check if the database exists, then delete it
        if sys_db.has_database(db_name):
            sys_db.delete_database(db_name)
            log.info(f"Database '{db_name}' deleted successfully.")
        else:
            log.error(f"Database '{db_name}' does not exist.")

        sys_db.create_database(db_name)
        log.info(f"New database '{db_name}' created successfully.")

    except Exception as e:
        log.error(f"Failed to authenticate with root: {e}")
        raise

except Exception as e:
    log.error(f"Failed to connect to ArangoDB server: {e}")
    raise


# Now creating the database
cfg = load_config(file="graph")
client = ArangoClient(hosts=os.getenv("ARANGO_HOST"))
db = client.db(
    os.getenv(database_name),
    username=os.getenv("ARANGO_USERNAME"),
    password=os.getenv("ARANGO_PASSWORD"),
)

# Vertex collections
for collection in cfg.get("vertex_collections", []):
    if not db.has_collection(collection):
        db.create_collection(collection)
        print(f"Created vertex collection: {collection}")

# Edge collections
for edge in cfg.get("edge_collections", []):
    name = edge["name"]
    if not db.has_collection(name):
        db.create_collection(name, edge=True)
        print(f"Created edge collection: {name}")
