import os
import logging
from typing import Optional
from dotenv import load_dotenv

from jira import JIRA
from atlassian import Jira  # for JQL queries

load_dotenv()
log = logging.getLogger(__name__)

# --- Module-level cache for JIRA client ---
_cached_jira_client: Optional[JIRA] = None


def get_jira_client() -> Optional[JIRA]:
    """
    Returns a cached JIRA client instance (initializes it on first call).
    """
    global _cached_jira_client

    # Return cached client if already initialized
    if _cached_jira_client is not None:
        log.debug("Returning cached JIRA client.")
        return _cached_jira_client

    # Initialize client if not cached
    log.info("Initializing new JIRA client...")
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_TOKEN = os.getenv("JIRA_TOKEN")

    try:
        jira_options = {"server": JIRA_SERVER_URL}
        jira = JIRA(options=jira_options, basic_auth=(JIRA_USERNAME, JIRA_TOKEN))
        log.info(f"Connected to JIRA: {JIRA_SERVER_URL}. Caching client.")
        _cached_jira_client = jira  # Store client to cache
        return _cached_jira_client
    except Exception as e:
        log.error(f"Failed to connect to JIRA: {e}")
        _cached_jira_client = None
        return None


def reset_jira_client_cache():
    """
    Resets the cached JIRA client.
    """
    global _cached_jira_client
    log.debug("Resetting cached JIRA client.")
    _cached_jira_client = None


def get_atlassian_client() -> Optional[Jira]:
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_TOKEN = os.getenv("JIRA_TOKEN")

    try:
        jira = Jira(
            url=JIRA_SERVER_URL, username=JIRA_USERNAME, password=JIRA_TOKEN, cloud=True
        )
        log.info(f"Connected to Jira: {JIRA_SERVER_URL}")
        return jira
    except Exception as e:
        log.error(f"Failed to connect to Jira: {e}")
        return None