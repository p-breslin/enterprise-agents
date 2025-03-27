import os
import logging
from dotenv import load_dotenv
from arango import ArangoClient
from utils.config import ConfigLoader


class GraphDBHandler:
    def __init__(self):
        load_dotenv()
        cfg = ConfigLoader("config").get_section("arango")
        try:
            client = ArangoClient(hosts=f"http://localhost:{cfg['port']}")
            self.db = client.db(
                cfg["dbname"],
                username=cfg["user"],
                password=os.getenv("ARANGO_PWD"),
            )
        except Exception as e:
            logging.error(f"Failed to connect to ArangoDB: {e}")

        # Vertex and Edge collections
        self.articles = self.db.collection("Articles")
        self.companies = self.db.collection("Companies")
        self.competes = self.db.collection("CompetesWith")

        # Not yet implemented
        self.products = self.db.collection("Products")
        self.produces = self.db.collection("Produces")

    def check_collection(self, name, edge=False):
        if not self.db.has_collection(name):
            self.db.create_collection(name, edge=edge)
            logging.info(f"Created collection: {name}")

    def insert_company(self, name):
        """Inserts a company if it does not already exist."""
        key = name.lower().replace(" ", "_")

        # Check if already exists
        existing = self.companies.get(key)
        if existing:
            logging.info(f" '{name}' already exists in DB.")
            return key

        # Insert if it does not exist
        self.companies.insert({"_key": key, "name": name})
        logging.info(f"Inserted new company: {name}")
        return key

    def insert_product(self, product_name):
        """Not yet implemented"""
        key = product_name.lower().replace(" ", "_")
        if not self.db.collection("Products").has(key):
            self.products.insert({"_key": key, "name": product_name})
        return key

    def create_relationship(self, collection, from_id, to_id):
        """Creates an edge between two nodes if it does not already exist."""
        query = f"""
        FOR e IN {collection}
            FILTER e._from == @from_id AND e._to == @to_id
            RETURN e
        """
        cursor = self.db.aql.execute(
            query, bind_vars={"from_id": from_id, "to_id": to_id}
        )

        # If any results exist; the relationship already exists
        if len(list(cursor)) > 0:
            logging.info(f"Edge already exists: {from_id} -> {to_id} in {collection}")
            return

        # Insert the relationship if it does not exist
        self.db.collection(collection).insert({"_from": from_id, "_to": to_id})
        logging.info(f"Created edge {from_id} -> {to_id} in {collection}")
