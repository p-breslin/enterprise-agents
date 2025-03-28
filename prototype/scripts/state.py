import operator
from typing import Any, Dict, Annotated, Optional
from dataclasses import dataclass, field


@dataclass(kw_only=True)
class InputState:
    """Defines the initial state after user input."""

    company: str


@dataclass(kw_only=True)
class OverallState:
    """The dynamically changing overall state of the system."""

    # Company to research as inputted by the user
    company: str

    # Output schema will be injected by the orchestrator
    output_schema: Dict[str, Any]

    # State for external data gathering
    search_queries: Optional[list[str]] = field(default=None)

    # Stores Tavily search results from EITHER vector DB OR web search
    search_results: list[Dict] = field(default=None)

    # LLM research; Annotated[...] ensures items are added instead of replaced, default_factory ensures each instance gets a new copy
    research: Annotated[list, operator.add] = field(default_factory=list)

    # Structured output
    final_output: Dict[str, Any] = field(default=None)

    # True if information is complete
    complete: bool = field(default=False)

    # Number of times the output has been revised
    revisions: int = field(default=0)


@dataclass(kw_only=True)
class OutputState:
    """Defines the output state to the User."""

    # Structured output
    final_output: Dict[str, Any]

    # Results from the Tavily searches
    search_results: list[Dict] = field(default=None)
