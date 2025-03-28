import os
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()


@dataclass(kw_only=True)
class ToolKeys:
    """API tool keys for the agents."""

    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
