import enum
from typing import Any, Dict
from dataclasses import dataclass, field


class EventType(str, enum.Enum):
    """Defines a set of named, constant values."""

    START_RESEARCH = "START_RESEARCH"

    # Graph query results
    GRAPH_DATA_FOUND = "GRAPH_DATA_FOUND"

    # Vector DB (no longer needed)
    DB_CHECK_DONE = "DB_CHECK_DONE"
    NEED_QUERIES = "NEED_QUERIES"

    # Need for external data gathering
    NEED_EXTERNAL_DATA = "NEED_EXTERNAL_DATA"
    QUERIES_GENERATED = "QUERIES_GENERATED"
    SEARCH_RESULTS_READY = "SEARCH_RESULTS_READY"

    # Processing and enrichment
    RESEARCH_COMPILED = "RESEARCH_COMPILED"
    EXTRACTION_COMPLETE = "EXTRACTION_COMPLETE"

    # Graph update result
    GRAPH_UPDATE_COMPLETE = "GRAPH_UPDATE_COMPLETE"

    # System events
    ERROR_OCCURRED = "ERROR_OCCURRED"
    SHUTDOWN = "SHUTDOWN"


@dataclass
class Event:
    """Stores event data."""

    # Identifier for the type of event
    type: EventType

    # Dictionary to hold event-related data
    payload: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        return f"Event({self.type}, {self.payload})"
