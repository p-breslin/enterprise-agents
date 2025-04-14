from typing import Optional, Dict, Any
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest


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
    print("\n[DEBUG] Full prompt sent to LLM:")
    for content in llm_request.contents:
        if content.role == "user":
            print(f"USER:\n{content.parts[0].text}\n")
        elif content.role == "system":
            print(f"SYSTEM:\n{content.parts[0].text}\n")
