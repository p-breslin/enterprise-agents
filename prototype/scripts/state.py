import operator
from typing import Any, Dict, Annotated
from dataclasses import dataclass, field


@dataclass(kw_only=True)
class OverallState:
    """
    The dynamically changing overall state of the system.
    default_factory ensures each instance gets a new copy.
    """

    # Company to research as inputted by the user
    company: str

    # Output schema will be injected by the orchestrator
    output_schema: Dict[str, Any]

    # State for external data gathering
    search_queries: list[str] = field(default_factory=list)

    # Stores results from web search tool
    search_results: list[Dict] = field(default_factory=list)

    # LLM research; Annotated[...] ensures items are added instead of replaced
    research: Annotated[list, operator.add] = field(default_factory=list)

    # Structured output
    final_output: Dict[str, Any] = field(default_factory=dict)

    # True if information is complete
    complete: bool = False

    # Number of times the output has been revised
    revisions: int = 0
