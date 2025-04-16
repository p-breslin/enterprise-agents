from typing import Optional, Dict, Any
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest

import json
from rich.panel import Panel
from rich.console import Console
from google.adk.events import Event

console = Console()


def trace_event(event: Event, debug_state: bool = False):
    # --- Event Author ---
    console.print(f"[bold blue][Event Author][/bold blue]: {event.author}")

    # --- Tool Calls ---
    for call in event.get_function_calls():
        console.print(
            Panel(
                f"[Tool Call] {call.name}\nArgs:\n{json.dumps(call.args, indent=2)}",
                title="[bold green]Tool Call[/bold green]",
                expand=True,
            )
        )

    # --- Final Output Trigger ---
    if event.is_final_response():
        console.print("[bold cyan]Final response detected[/bold cyan]")

    # --- Errors ---
    if event.error_code:
        console.print(
            Panel(
                f"[Error Code] {event.error_code}\nMessage: {event.error_message}",
                title="[bold red]Agent Error[/bold red]",
                expand=True,
            )
        )

    # --- State Changes ---
    if debug_state and event.actions and event.actions.state_delta:
        console.print(
            Panel(
                f"[State Change]\n{json.dumps(event.actions.state_delta, indent=2)}",
                title="[bold magenta]State Delta[/bold magenta]",
                expand=True,
            )
        )


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


def save_trace_event(event: Event, test_name):
    output_lines = []

    # Event Author
    output_lines.append(f"\n[{test_name}] Event: {event.author}")

    # Tool Calls
    if event.get_function_calls():
        for call in event.get_function_calls():
            output_lines.append(f"[Tool Call] {call.name} | Args: {call.args}")

    # Final Response
    if event.is_final_response():
        output_lines.append("Final response detected")

    # Combine
    output = "\n".join(output_lines)

    # Save to file
    with open("graph_update_trace.log", "a") as f:
        f.write(output + "\n")
