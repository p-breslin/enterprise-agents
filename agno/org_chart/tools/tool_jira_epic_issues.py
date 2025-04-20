import json
import logging
from agno.tools import tool
from utils_agno import get_jira_client

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# --- Jira Tool Function: Search Issues from Epics ---
@tool()
def jira_get_epic_issues(epic_key: str, max_results: int = 50) -> str:
    """
    Searches for Jira issues belonging to a specific Epic using a JQL query

    This tool queries Jira to find issues linked to the provided Epic key via the 'parent' field (common in Jira Cloud). It returns a list of raw issue data dictionaries as received from the Jira API, limited to essential fields
    (key, summary, status, assignee) needed for further processing by the agent.

    **IMPORTANT for Agent:** The agent is responsible for iterating through the returned list and extracting specific details (like status name or assignee display name) from the nested 'fields' object within each dictionary.

    Args:
        epic_key (str): The key of the Epic issue (e.g., 'PROJ-123'). REQUIRED.
        max_results (int): Maximum number of issues to return. Defaults to 50.

    Returns:
        str: A A JSON string representation of a list of raw issue data dictionaries directly from the Jira API response. Each A JSON string representation of the dictionary typically contains:
            - 'key' (str): The issue key (e.g., 'PROJ-456')
            - 'id' (str): The internal issue ID.
            - 'self' (str): URL to the issue API endpoint.
            - 'fields' (Dict): A nested dictionary containing:
                - 'summary' (str | None): Issue title.
                - 'status' (Dict | None): {'name': 'Status Name', ...}
                - 'assignee' (Dict | None): {'displayName': 'Assignee

        Returns an empty A JSON string representation of a list if no issues are found. Returns a A JSON string representation os a list containing a single error dictionary (e.g., [{"error": "message"}]) if an error occurs.
    """
    logger.info(
        f"Tool 'search_jira_issues_by_epic' called for Epic: {epic_key} (limit: {max_results})"
    )
    jira = get_jira_client()
    if not jira:
        return json.dumps(
            [
                {
                    "error": "Failed to initialize Jira client. Check credentials and environment variables."
                }
            ]
        )

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
            return json.dumps(raw_issues)
        else:
            logger.info(f"No issues found for Epic {epic_key} with JQL: {jql_query}")
            return json.dumps([])  # Return empty list

    except Exception as e:
        logger.error(f"Error during Jira JQL search for Epic {epic_key}: {e}")
        error_message = f"An error occurred while searching Jira: {str(e)}"
        if "does not exist" in str(e):
            error_message = f"Epic '{epic_key}' not found or JQL query failed."
        return json.dumps([{"error": error_message}])
