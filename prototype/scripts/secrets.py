import os
from dotenv import load_dotenv
from dataclasses import dataclass, field

load_dotenv()


@dataclass(kw_only=True)
class Secrets:
    """API tool keys for the agents."""

    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # ArangoDB Connection Details
    ARANGO_PORT: str = field(default=os.getenv("ARANGO_PORT"))
    ARANGO_DB: str = field(default=os.getenv("ARANGO_DB"))
    ARANGO_USR: str = field(default=os.getenv("ARANGO_USR"))
    ARANGO_PWD: str = field(default=os.getenv("ARANGO_PWD"))
