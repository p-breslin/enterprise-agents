from typing import Optional, Dict, Any
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

def debug_before_tool(
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext
) -> Optional[Dict]:
    print("[DEBUG] Tool Call:")
    print(f"  Tool name: {tool.name}")
    print(f"  Args: {args}")
    print(f"  Agent: {tool_context.agent_name}")
    return None  # Let the tool run normally