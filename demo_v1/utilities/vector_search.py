import logging
import weaviate


class EmbeddingSearch:
    def __init__(self, query):
        self.results = None
        self.query = query

        # Initialize database client and collection
        self.client = None
        self.cfg = {
            "port": 8080,
            "dbname": "ArticleEmbeddings",
            "schema": [
                {"name": "title", "dataType": "text", "skip": True},
                {"name": "hash", "dataType": "text", "skip": True},
                {"name": "link", "dataType": "text", "skip": True},
                {"name": "published", "dataType": "date", "skip": True},
                {"name": "tags", "dataType": "text[]", "skip": True},
                {"name": "content", "dataType": "text", "skip": False},
            ],
            "fields": ["title", "hash", "link", "published", "tags", "content"],
        }

        try:
            self.client = weaviate.connect_to_local(port=self.cfg["port"])
            self.collection = self.client.collections.get(self.cfg["dbname"])
            logging.info("Weaviate initialized successfully.")
        except Exception as e:
            logging.error(f"Weaviate Initialization Failed: {e}")
            self.collection = None

    def search(self, N=1):
        """Performs a similarity search on the database."""
        self.results = self.collection.query.near_text(query=self.query, limit=N)

    def retrieve_data(self):
        """Extracts the data we want from the embedding search results."""

        retrieved_data = {}

        # Results are stored in a list of Objects
        for obj in self.results.objects:
            for field in self.cfg["fields"]:
                retrieved_data[field] = obj.properties[field]
            break

        if retrieved_data:
            llm_context = retrieved_data["content"]
            return retrieved_data, llm_context
        else:
            return None, None

    def run(self):
        self.search()
        retrieved_data, llm_context = self.retrieve_data()
        self.client.close()
        return retrieved_data, llm_context
