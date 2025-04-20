import logging
from agno.agent import tool
from typing import Dict, Any
from utils_agno import get_jira_client

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# --- Jira Tool Function: Get Issue (e.g. Story from Epic) ---
@tool()
def jira_get_issue(issue_key: str) -> Dict[str, Any]:
    """
    Retrieves the details of a single Jira issue by its key.

    This tool fetches the full data available for a specific Jira issue. The agent using this tool will need to parse the returned dictionary to extract the specific fields it requires (e.g., summary, status.name, fields assignee.displayName).

    Args:
        issue_key (str): The key of the Jira issue to retrieve (e.g., 'PROJ-123'). REQUIRED.

    Returns:
        Dict[str, Any]: A dictionary containing the full details of the Jira issue if found. Returns a dictionary containing an "error" key if the issue is not found, if there's a connection problem, or if any other error occurs.
    """
    logger.info(f"Tool 'jira_get_issue' called for Issue Key: {issue_key}")
    jira = get_jira_client()
    if not jira:
        return {"error": "Jira client initialization failed."}

    try:
        # Fetch issue details. By default, it fetches many fields.
        # You could add 'fields' param if you know exactly what's needed, e.g.,
        # issue_data = jira.issue(issue_key, fields="summary,status,assignee,created,...")
        issue_data = jira.issue(issue_key)

        if issue_data:
            logger.info(f"Successfully retrieved issue details for {issue_key}.")
            return issue_data  # Return the full issue dictionary
        else:
            # This path might not be reachable if jira.issue raises on 404
            logger.warning(
                f"Jira API returned no data for issue {issue_key}, treating as not found."
            )
            return {"error": f"Issue '{issue_key}' not found or no data returned."}

    except Exception as e:
        logger.error(f"Error retrieving Jira issue {issue_key}: {e}", exc_info=True)
        error_message = (
            f"An error occurred while retrieving issue '{issue_key}': {str(e)}"
        )

        # Handle common errors specifically
        if "404" in str(e) or "Not Found" in str(e):
            error_message = f"Issue '{issue_key}' not found."
        elif "401" in str(e) or "Unauthorized" in str(e):
            error_message = "Authentication failed. Check Jira permissions."
        elif "403" in str(e) or "Forbidden" in str(e):
            error_message = f"Permission denied to view issue '{issue_key}'."

        return {"error": error_message}
