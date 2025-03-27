import os
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()


@dataclass(kw_only=True)
class Configuration:
    """Configurable parameters for the agents."""

    # API Keys
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # Number of search queries per company
    N_searches: int = 1

    # Number of revisions to the final output
    N_revisions: int = 0

    TAVILY_SEARCH_PARAMS = {
        "search_depth": "basic",
        "max_results": 3,
        "time_range": "month",
        "topic": "general",
        "include_raw_content": True,
    }
