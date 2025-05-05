import os
import logging
from typing import Optional
from dotenv import load_dotenv
from github import Github, GithubException

load_dotenv()
log = logging.getLogger(__name__)

# Module-level cache for the GitHub client
_cached_github_client: Optional[Github] = None


def get_github_client() -> Optional[Github]:
    """
    Returns a cached PyGithub client instance (initializes it on first call).
    Requires GITHUB_PERSONAL_ACCESS_TOKEN environment variable.
    """
    global _cached_github_client

    # Return cached client if already initialized
    if _cached_github_client is not None:
        log.debug("Returning cached GitHub client.")
        return _cached_github_client

    # Initialize client if not cached
    log.info("Initializing new GitHub client...")
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        log.error("GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set.")
        return None

    try:
        gh = Github(token)
        # Verify connection/token by getting authenticated user
        user = gh.get_user()
        log.info(f"Successfully connected to GitHub as user: {user.login}")
        _cached_github_client = gh  # Store client to cache
        return _cached_github_client

    except GithubException as e:
        log.error(f"Failed to connect to GitHub or authenticate: {e.status} {e.data}")
        _cached_github_client = None
        return None
    except Exception as e:
        log.error(
            f"An unexpected error occurred during GitHub client initialization: {e}",
            exc_info=True,
        )
        _cached_github_client = None
        return None


def reset_github_client_cache():
    """
    Resets the cached GitHub client (useful for testing).
    """
    global _cached_github_client
    log.debug("Resetting cached GitHub client.")
    _cached_github_client = None
