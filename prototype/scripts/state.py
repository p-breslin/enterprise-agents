import operator
from typing import Any, Dict, List, Annotated
from dataclasses import dataclass, field

# # Specific to OpenAI API
# DEFAULT_SCHEMA = {
#     "type": "json_schema",
#     "json_schema": {
#         "name": "company_info",
#         "schema": {
#             "type": "object",
#             "properties": {
#                 "company_name": {
#                     "type": "string",
#                     "description": "Official name of the company",
#                 },
#                 "product_description": {
#                     "type": "string",
#                     "description": "Brief description of the company's main product or service",
#                 },
#             },
#             "additionalProperties": False,
#             "required": ["company_name", "product_description"],
#         },
#         "strict": True,
#     },
# }


@dataclass(kw_only=True)
class InputState:
    """Defines the initial state after user input."""

    company: str


@dataclass(kw_only=True)
class OverallState:
    """The dynamically changing overall state of the system."""

    # Company to research as inputted by the user
    company: str

    # Output schema is injected by the orchestrator
    output_schema: Dict[str, Any]

    # Generated search queries for finding new information
    search_queries: List[str] = field(default=None)

    # Results from the Tavily searches
    search_results: List[Dict] = field(default=None)

    # LLM research; Annotated[...] ensures items are added instead of replaced, default_factory ensures each instance gets a new copy
    research: Annotated[List, operator.add] = field(default_factory=List)

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
    search_results: List[Dict] = field(default=None)
