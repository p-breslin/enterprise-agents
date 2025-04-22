import json
import datetime
from pathlib import Path
from pydantic import BaseModel
from typing import Iterator, Union, Optional, Dict, Any, List

from rich.syntax import Syntax
from rich.console import Console
from agno.agent import RunResponse


console = Console()
CALLBACK_LOG_DIR = Path("tests/test_callbacks")


# Helper to serialize content appropriately
def serialize_content(data: Any) -> Any:
    """
    Attempts to serialize data, preferring Pydantic dump.
    """
    if isinstance(data, BaseModel):
        try:
            return data.model_dump(mode="json")
        except Exception:
            return repr(data)  # repr if model_dump fails for some reason
    else:
        try:
            # If directly JSON serializable
            json.dumps(data)
            return data
        except TypeError:
            return repr(data)  # then repr for non-serializable unknown types


def log_agno_callbacks(
    response: Union[RunResponse, Iterator[RunResponse]],
    run_label: str,
    filename: Optional[str] = None,
    overwrite=True,
):
    """
    Logs key events and tool calls from an Agno RunResponse or stream.

    Args:
        response: The RunResponse object or iterator from agent.run().
        run_label: A descriptive label for this run (e.g., test name).
        filename: Optional filename to save the log within the predefined CALLBACK_LOG_DIR.
        overwrite: Determines if callbacks saved file are written over appended.
    """

    console.print(
        f"\n--- Agno Callbacks: [bold cyan]{run_label}[/bold cyan] ---",
        style="bold blue",
    )

    log_entries: List[Dict[str, Any]] = []
    output_path = None

    # Construct the full path if a filename is given
    if filename:
        CALLBACK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        output_path = CALLBACK_LOG_DIR / f"{filename}.jsonl"

    # --- Process Response(s) ---
    chunks_to_process: List[RunResponse] = []
    is_stream = isinstance(response, Iterator)

    if is_stream:
        console.print("[italic]Processing Stream...[/italic]")

        try:
            # Consume the iterator into a list
            chunks_to_process = list(response)
            if not chunks_to_process:
                console.print("[yellow]Warning: Stream yielded no chunks.[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Error consuming stream iterator: {e}[/bold red]")
            if output_path:
                log_entries.append(
                    {
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "run_label": run_label,
                        "error": f"Error consuming stream: {e}",
                    }
                )

    elif isinstance(response, RunResponse):
        console.print("[italic]Processing Non-Streamed Response...[/italic]")
        chunks_to_process.append(response)
    else:
        console.print(
            f"[bold red]Error: Invalid response type: {type(response)}[/bold red]"
        )
        return  # Exit if invalid type

    # --- Loop through Chunks (will be 1 if non-streamed) ---
    for i, chunk in enumerate(chunks_to_process):
        if not isinstance(chunk, RunResponse):
            console.print(
                f"[bold red]Error: Item {i} in chunks_to_process is not a RunResponse object (type: {type(chunk)}). Skipping.[/bold red]"
            )
            continue
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Attributes to log
        event_type = getattr(chunk, "event", "['event' Missing]")
        event_data = getattr(chunk, "event_data", None)
        run_id = getattr(chunk, "run_id", "['run_id' Missing]")
        session_id = getattr(chunk, "session_id", "['session_id' Missing]")
        agent_id = getattr(chunk, "agent_id", None)
        model = getattr(chunk, "model", None)
        metrics = getattr(chunk, "metrics", None)
        content = getattr(chunk, "content", None)
        content_type = getattr(chunk, "content_type", None)
        event_type = chunk.event or "[No Event Type]"
        event_data = getattr(chunk, "event_data", None)

        # Mark final chunk
        is_final_chunk = not is_stream or (i == len(chunks_to_process) - 1)

        console.print(
            f"\n[dim]----- Chunk {i + 1}{' (Final)' if is_final_chunk else ''} ----- [/dim]"
        )
        console.print(f"[bold]Timestamp:[/bold] {timestamp}")
        console.print(f"[bold]Event:[/bold] [yellow]{event_type}[/yellow]")
        console.print(f"[bold]Run ID:[/bold] {run_id}")
        console.print(f"[bold]Session ID:[/bold] {session_id}")

        # Simple tool call indication
        is_tool_event = isinstance(event_type, str) and "tool" in event_type.lower()
        if is_tool_event:
            console.print("[bold cyan]Tool-related Event Detected[/bold cyan]")

        # Print event data using JSON syntax highlighting for clarity
        if event_data:
            console.print("[bold]Event Data:[/bold]")
            try:
                # Pretty print JSON-like data (and str for non JSON)
                data_str = json.dumps(event_data, indent=2, default=str)
                syntax = Syntax(
                    data_str,
                    "json",
                    theme="default",
                    line_numbers=False,
                    word_wrap=True,
                )
                console.print(syntax)
            except TypeError:
                # Fallback for non-serializable data
                console.print(
                    f"[italic yellow] (Could not JSON serialize, raw):[/italic] {str(event_data)}"
                )
        else:
            console.print("[italic]No Event Data[/italic]")

        # --- Prepare Log Entry ---
        if output_path:
            # Serialize content specifically for the log file
            log_content = serialize_content(content) if is_final_chunk else None

            log_entry = {
                "timestamp": timestamp,
                "run_label": run_label,
                "run_id": run_id,
                "session_id": session_id,
                "agent_id": agent_id,
                "event": event_type,
                "event_data": event_data,
                "is_final_chunk": is_final_chunk,
                "model": model,
                "metrics": metrics if is_final_chunk else None,
                "content": log_content,
                "content_type": content_type if is_final_chunk else None,
            }
            log_entries.append(log_entry)

    # --- Write logs to file ---
    write_type = "w" if overwrite else "a"
    if output_path and log_entries:
        try:
            with open(output_path, f"{write_type}", encoding="utf-8") as f:
                for entry in log_entries:
                    # Ensure serializability for JSON Lines
                    json_line = json.dumps(entry, default=str)
                    f.write(json_line + "\n")
            console.print(
                f"\nCallbacks written to: [bold green]{output_path}[/bold green]"
            )
        except Exception as e:
            console.print(
                f"\n[bold red]Error writing callbacks to file {output_path}: {e}[/bold red]"
            )

    console.print(
        f"\n--- End Callbacks: [bold cyan]{run_label}[/bold cyan] ---",
        style="bold blue",
    )
