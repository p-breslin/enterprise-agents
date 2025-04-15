import os
import logging
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

from atlassian import Jira

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_jira_client() -> Optional[Jira]:
    load_dotenv()
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_TOKEN = os.getenv("JIRA_TOKEN")

    try:
        jira = Jira(
            url=JIRA_SERVER_URL, username=JIRA_USERNAME, password=JIRA_TOKEN, cloud=True
        )
        logger.info(f"Connected to Jira: {JIRA_SERVER_URL}")
        return jira
    except Exception as e:
        logger.error(f"Failed to connect to Jira: {e}")
        return None


def jira_get_epic_issues(
    epic_key: str, max_results: int = 50
) -> List[Dict[str, Any]]:
    """
    Searches for Jira issues belonging to a specific Epic using a JQL query

    This tool queries Jira to find issues linked to the provided Epic key via the 'parent' field (common in Jira Cloud). It returns a list of raw issue data dictionaries as received from the Jira API, limited to essential fields
    (key, summary, status, assignee) needed for further processing by the agent.

    **IMPORTANT for Agent:** The agent is responsible for iterating through the returned list and extracting specific details (like status name or assignee display name) from the nested 'fields' object within each dictionary.

    Args:
        epic_key (str): The key of the Epic issue (e.g., 'PROJ-123'). REQUIRED.
                        (ADK Best Practice: Minimal, meaningful parameters)
        max_results (int): Maximum number of issues to return. Defaults to 50.
                        (ADK Best Practice: Simple data types)

    Returns:
        List[Dict[str, Any]]: A list of raw issue data dictionaries directly from the Jira API response. Each dictionary typically contains:
            - 'key' (str): The issue key (e.g., 'PROJ-456')
            - 'id' (str): The internal issue ID.
            - 'self' (str): URL to the issue API endpoint.
            - 'fields' (Dict): A nested dictionary containing:
                - 'summary' (str | None): Issue title.
                - 'status' (Dict | None): {'name': 'Status Name', ...}
                - 'assignee' (Dict | None): {'displayName': 'Assignee

        Returns an empty list if no issues are found.
        Returns a list containing a single error dictionary (e.g., [{"error": "message"}]) if an error occurs. (ADK Best Practice: Return dictionary-like structures. Docstring clearly describes expected return value for LLM.)
    """
    logger.info(
        f"Tool 'search_jira_issues_by_epic' called for Epic: {epic_key} (limit: {max_results})"
    )
    jira = get_jira_client()
    if not jira:
        # ADK Best Practice: Return meaningful error messages in a dictionary
        return [
            {
                "error": "Failed to initialize Jira client. Check credentials and environment variables."
            }
        ]

    # JQL query targeting 'parent' field
    jql_query = f'parent = "{epic_key}" ORDER BY created DESC'
    logger.info(f"Executing JQL: {jql_query}")

    try:
        # Request ONLY the necessary fields for efficiency
        issues_data = jira.jql(
            jql_query,
            limit=max_results,
            fields="key,summary,status,assignee",  # Critical for efficiency
        )

        if issues_data and "issues" in issues_data:
            raw_issues = issues_data["issues"]
            logger.info(f"Found {len(raw_issues)} raw issues for Epic {epic_key}.")
            # Return the raw list directly to the agent
            return raw_issues
        else:
            logger.info(f"No issues found for Epic {epic_key} with JQL: {jql_query}")
            return []  # Return empty list

    except Exception as e:
        logger.error(f"Error during Jira JQL search for Epic {epic_key}: {e}")
        error_message = f"An error occurred while searching Jira: {str(e)}"
        if "does not exist" in str(e):
            error_message = f"Epic '{epic_key}' not found or JQL query failed."
        # ADK Best Practice: Return descriptive error
        return [{"error": error_message}]  # Return error in a list for type consistency
