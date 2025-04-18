import os
import logging
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s - %(message)s",
)


def arango_connect(db_name="ARANGO_DB_JIRA"):
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
        logging.info(f"Successfully connected to ArangoDB: {HST}, DB: {DB}")
        return conn

    except Exception as e:
        logging.error(f"Failed to connect to ArangoDB server: {e}")
        raise
