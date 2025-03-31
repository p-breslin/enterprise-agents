import os
import logging
from dotenv import load_dotenv
from arango import ArangoClient
from secrets import Secrets

"""
Deletes the ArangoDB database.
"""

# Load environment variables
load_dotenv()
secrets = Secrets()

try:
    # Connect to ArangoDB server
    client = ArangoClient(hosts=secrets.ARANGO_HOST)

    try:
        # Authenticate with root user (required to manage databases)
        sys_db = client.db("_system", username="root", password=os.getenv("ARANGO_PWD"))

        db_name = secrets.ARANGO_DB

        # Check if the database exists, then delete it
        if sys_db.has_database(db_name):
            sys_db.delete_database(db_name)
            logging.info(f"Database '{db_name}' deleted successfully.")
        else:
            logging.info(f"Database '{db_name}' does not exist.")

    except Exception as e:
        logging.error(f"Failed to authenticate with root: {e}")
        raise

except Exception as e:
    logging.error(f"Failed to connect to ArangoDB server: {e}")
    raise
