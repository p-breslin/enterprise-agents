import os
import json
import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv
from arango import ArangoClient

load_dotenv()
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s - %(message)s",
)


def load_prompt(prompt_key: str) -> str:
    path = Path(__file__).parent / "prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt_key]


def load_config(folder):
    path = Path(__file__).parent / f"configs/{folder}.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def log_event_details(event):
    """
    Prints a detailed summary of the content inside an ADK event, identifying tool calls, responses, thoughts, text, and more.
    """
    author = event.author or "unknown"

    if event.content and event.content.parts:
        for i, part in enumerate(event.content.parts):
            if part.function_call:
                print(
                    f"[{author}] Tool function call: {part.function_call.name}({json.dumps(part.function_call.args)})"
                )

            elif part.function_response:
                print(f"[{author}] Results received from {part.function_response.name}")

            elif part.text:
                print(f"[{author}] LLM response generated")

            elif part.thought:
                print(f"[{author}] Thought: {part.thought.text}")

            elif part.code_execution_result:
                print(f"[{author}] Code result: {part.code_execution_result}")

            elif part.executable_code:
                print(f"[{author}] Code to run")

            elif part.file_data:
                print(f"[{author}] File sent: {part.file_data.file_name}")

            else:
                print(f"[{author}] Unknown content part: {part}")
    else:
        print(f"[{author}] Event had no content.")


def save_json(data, filename="jira_issues.json"):
    """
    Saves structured data to a JSON file.
    """
    output = Path(__file__).parent / filename

    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Structured data saved to: {output}")


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
