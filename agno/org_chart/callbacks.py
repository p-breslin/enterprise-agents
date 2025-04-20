import json
from agno.agent import RunResponse
from typing import Iterator, Union

from rich.panel import Panel
from rich.console import Console
from rich.syntax import Syntax

console = Console()


def print_callbacks(
    response: Union[RunResponse, Iterator[RunResponse]],
    test_name: str,
    print_content: bool = True,
    print_tools: bool = True,
    print_metrics: bool = True,
):
    """
    Prints key details from an Agno RunResponse or stream.
    """

    console.print(f"\n--- {test_name} Run Response Details ---", style="bold blue")

    final_response = None
    if isinstance(response, Iterator):
        console.print("[italic]Processing Stream...[/italic]")
        streamed_content = ""
        content_type = "str"  # Default assumption
        for chunk in response:
            if chunk.content:
                streamed_content += str(
                    chunk.content
                )  # Assuming string content for now
                content_type = chunk.content_type
            final_response = chunk  # Keep the last chunk for final details
        console.print(
            Panel(streamed_content, title="Streamed Content", border_style="green")
        )
        if final_response:
            final_response.content = streamed_content  # Aggregate content
            final_response.content_type = content_type
    else:
        final_response = response

    if not final_response:
        console.print("[bold red]No final response object found.[/bold red]")
        return

    console.print(f"Run ID: {final_response.run_id}")
    console.print(f"Agent ID: {final_response.agent_id}")
    console.print(f"Session ID: {final_response.session_id}")
    console.print(f"Model Used: {final_response.model}")

    if print_content and final_response.content:
        title = f"Final Content (type: {final_response.content_type})"
        content_display = ""
        if isinstance(final_response.content, (dict, list)):
            content_display = json.dumps(final_response.content, indent=2)
            syntax = Syntax(
                content_display, "json", theme="default", line_numbers=False
            )
            console.print(
                Panel(syntax, title=title, border_style="yellow", expand=False)
            )
        elif isinstance(final_response.content, object) and hasattr(
            final_response.content, "model_dump_json"
        ):  # Handle Pydantic models
            content_display = final_response.content.model_dump_json(indent=2)
            syntax = Syntax(
                content_display, "json", theme="default", line_numbers=False
            )
            console.print(
                Panel(syntax, title=title, border_style="yellow", expand=False)
            )
        else:
            content_display = str(final_response.content)
            console.print(
                Panel(content_display, title=title, border_style="yellow", expand=False)
            )

    # Note: Tool calls are usually part of intermediate steps, not the final RunResponse unless show_tool_calls=True on Agent
    # Agno's debug_mode=True is better for seeing internal tool calls.
    # This simplistic view checks if tools were *provided* to the model in the last step.
    if print_tools and final_response.tools:
        tool_names = [
            t.get("function", {}).get("name", "unknown") for t in final_response.tools
        ]
        console.print(
            Panel(
                f"Tools Provided to Model: {', '.join(tool_names)}",
                title="Tools",
                border_style="cyan",
            )
        )

    if print_metrics and final_response.metrics:
        metrics_str = json.dumps(final_response.metrics, indent=2)
        syntax = Syntax(metrics_str, "json", theme="default", line_numbers=False)
        console.print(Panel(syntax, title="Metrics", border_style="magenta"))

    console.print("--- End Response Details ---", style="bold blue")
