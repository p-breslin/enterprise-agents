import uuid
import unittest
from scripts.secrets import Secrets
from utilities.graph_db import ArangoDBManager


class TestBuildFilter(unittest.TestCase):
    """
    Unit test for ArangoDBManager._build_filter method (graph_db.py).
    """

    def setUp(self):
        self.test_company = "Nvidia"
        self.test_industry = "AI"

    def test_single_filter(self):
        """
        Basic single-key dictionary.
        """
        filters = {"name": self.test_company}
        expected = "doc.name == @name"
        result = ArangoDBManager._build_filter("doc", filters)
        self.assertEqual(result, expected)

    def test_multiple_filters(self):
        """
        Multi-key dictionary.
        """
        filters = {"name": self.test_company, "industry": self.test_industry}
        result = ArangoDBManager._build_filter("doc", filters)
        expected_options = [
            "doc.name == @name AND doc.industry == @industry",
            "doc.industry == @industry AND doc.name == @name",
        ]
        self.assertIn(result, expected_options)


class TestArangoDBLive(unittest.TestCase):
    """
    Integration tests using a live ArangoDB instance.
    """

    @classmethod
    def setUpClass(cls):
        secrets = Secrets()
        cls.db = ArangoDBManager(
            host=secrets.ARANGO_HOST,
            db_name=secrets.ARANGO_DB,
            usr=secrets.ARANGO_USR,
            pwd=secrets.ARANGO_PWD,
        )
        cls.test_collection = "TestCollection"
        cls.test_edge_collection = "TestEdges"

        # Ensure collections exist before running any tests
        cls.db.ensure_collections(
            [{"name": cls.test_collection}],
            [{"name": cls.test_edge_collection}],
        )

    def setUp(self):
        """
        Runs before every test to ensure NodeA and NodeB exist and return IDs.
        """
        self.doc_a = self.db.find_or_create_document(
            collection_name=self.test_collection,
            filter_dict={"name": "NodeA"},
            document_data={"name": "NodeA"},
        )
        self.doc_b = self.db.find_or_create_document(
            collection_name=self.test_collection,
            filter_dict={"name": "NodeB"},
            document_data={"name": "NodeB"},
        )

    def test_find_or_create_document(self):
        unique_name = f"TestEntity_{uuid.uuid4()}"
        doc = {"name": unique_name, "type": "test"}

        result = self.db.find_or_create_document(
            collection_name=self.test_collection,
            filter_dict={"name": unique_name},
            document_data=doc,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], unique_name)

    def test_find_or_create_edge(self):
        edge = self.db.find_or_create_edge(
            edge_collection_name=self.test_edge_collection,
            from_doc_id=self.doc_a["_id"],
            to_doc_id=self.doc_b["_id"],
            edge_data={"label": "connects"},
        )

        self.assertIsNotNone(edge)
        self.assertEqual(edge["_from"], self.doc_a["_id"])
        self.assertEqual(edge["_to"], self.doc_b["_id"])

    def test_execute_aql(self):
        for node in ["NodeA", "NodeB"]:
            with self.subTest(node=node):
                query = f"""
                FOR doc IN {self.test_collection}
                    FILTER doc.name == @name
                    RETURN doc
                """
                result = self.db.execute_aql(query, bind_vars={"name": node})
                print(f"AQL result for '{node}': {result}")
                self.assertTrue(isinstance(result, list))
                self.assertGreaterEqual(len(result), 1)
                self.assertEqual(result[0]["name"], node)

    @classmethod
    def tearDownClass(cls):
        """
        Delete entire test collections at the very end of all tests.
        """
        try:
            if cls.db.db.has_collection(cls.test_collection):
                cls.db.db.delete_collection(cls.test_collection, ignore_missing=False)
                print(f"Deleted collection: {cls.test_collection}")

            if cls.db.db.has_collection(cls.test_edge_collection):
                cls.db.db.delete_collection(
                    cls.test_edge_collection, ignore_missing=False
                )
                print(f"Deleted edge collection: {cls.test_edge_collection}")

        except Exception as e:
            print(f"Error deleting test collections: {e}")


if __name__ == "__main__":
    unittest.main()
