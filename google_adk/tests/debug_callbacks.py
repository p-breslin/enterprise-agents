from typing import Optional, Dict, Any
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest

from google.adk.events import Event


def trace_event(event: Event):
    print(f"\n[Event Author]: {event.author}")

    if event.get_function_calls():
        for call in event.get_function_calls():
            print(f"[Tool Call] {call.name} | Args: {call.args}")

    elif event.get_function_responses():
        for res in event.get_function_responses():
            print(f"[Tool Response] {res.name}")

    if event.is_final_response():
        print("Final response detected")


def debug_before_tool(
    tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext
) -> Optional[Dict]:
    print("\n[DEBUG] Tool Call:")
    print(f"  Tool name: {tool.name}")
    print(f"  Args: {args}")
    print(f"  Agent: {tool_context.agent_name}")
    return None  # Let the tool run normally


def debug_before_model(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    print("\n[DEBUG] Query sent to LLM:")
    for content in llm_request.contents:
        if content.role == "user":
            print(f"USER: {content.parts[0].text}\n")
        elif content.role == "system":
            print(f"SYSTEM: {content.parts[0].text}\n")
    return None
