import os
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()


def main():
    # Configure the ArangoDB client with the host details
    client = ArangoClient(hosts="http://arango.xflow-in.dev")

    # Connect to the "_system" database with appropriate credentials
    sys_db = client.db(
        "_system", username="root", password=os.getenv("ARANGO_XFLOW_PWD")
    )

    # Get the list of databases
    databases = sys_db.databases()

    # Print the list of databases
    # print("Databases available:", databases)

    # Print the count of databases
    print("Total number of databases:", len(databases))


if __name__ == "__main__":
    main()
