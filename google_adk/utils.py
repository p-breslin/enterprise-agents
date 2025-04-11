import json
import yaml
from pathlib import Path


def load_prompt(prompt_key: str) -> str:
    path = Path(__file__).parent / "prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt_key]


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
                # preview = part.text.strip().replace("\\n", " ")[:100]
                # print(
                #     f"Text from {author}:\n{preview}{'...' if len(part.text) > 100 else ''}"
                # )
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