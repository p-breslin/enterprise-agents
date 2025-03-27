import operator
from typing import Any, Annotated
from dataclasses import dataclass, field

# Specific to OpenAI API
DEFAULT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "company_info",
        "schema": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Official name of the company",
                },
                "product_description": {
                    "type": "string",
                    "description": "Brief description of the company's main product or service",
                },
            },
            "additionalProperties": False,
            "required": ["company_name", "product_description"],
        },
        "strict": True,
    },
}


@dataclass(kw_only=True)
class InputState:
    """Defines the initial state after user input."""

    # Company to research as inputted by the user
    company: str

    # Schema defining the output format for the agent
    output_schema: dict[str, Any] = field(default_factory=lambda: DEFAULT_SCHEMA)


@dataclass(kw_only=True)
class OverallState:
    """The dynamically changing overall state of the system."""

    # Company to research as inputted by the user
    company: str

    # Output schema; default_factory ensures each instance gets a new copy
    output_schema: dict[str, Any] = field(default_factory=lambda: DEFAULT_SCHEMA)

    # Generated search queries for finding new information
    search_queries: list[str] = field(default=None)

    # Results from the Tavily searches
    search_results: list[dict] = field(default=None)

    # LLM research; Annotated[...] ensures items are added instead of replaced
    research: Annotated[list, operator.add] = field(default_factory=list)

    # Structured output
    final_output: dict[str, Any] = field(default=None)

    # True if information is complete
    complete: bool = field(default=None)

    # Number of times the output has been revised
    revisions: int = field(default=0)


@dataclass(kw_only=True)
class OutputState:
    """Defines the output state to the User."""

    # Structured output
    final_output: dict[str, Any]

    # Results from the Tavily searches
    search_results: list[dict] = field(default=None)
