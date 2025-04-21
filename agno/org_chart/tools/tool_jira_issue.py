import json
import logging
from agno.tools import tool
from utils_agno import get_jira_client

logging.basicConfig(
    level=logging.INFO, format="%(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Define the specific fields to be returned ---
_REQUIRED_ISSUE_FIELDS = [
    "key",
    "summary",
    "status",
    "assignee",
    "created",
    "resolutiondate",
    "priority",
    "project",
]
_REQUIRED_FIELDS_STR = ",".join(_REQUIRED_ISSUE_FIELDS)


# --- Jira Tool Function: Get Issue (e.g. Story from Epic) ---
@tool()
def jira_get_issue(issue_key: str) -> str:
    """
    Purpose of Tool:
        Retrieves the SPECIFIC details of a single Jira issue by its key as a JSON string. The agent using this tool will need to parse the returned dictionary to extract the specific fields it requires (e.g., summary, status.name, fields assignee.displayName).

    Args:
        issue_key (str): The key of the Jira issue to retrieve (e.g., 'PROJ-123'). REQUIRED.

    Returns:
        str: A JSON string representation of a dictionary containing the requested issue fields if found. Returns JSON string of an error object if an error occurs.
    """
    logger.info(f"Tool 'jira_get_issue' called for Issue Key: {issue_key}")
    jira = get_jira_client()
    if not jira:
        return json.dumps([{"error": "Jira client initialization failed."}])

    try:
        # Fetch the specific issue details as defined above
        logger.debug(f"Requesting fields: {_REQUIRED_FIELDS_STR} for issue {issue_key}")
        issue_data = jira.issue(issue_key, fields=_REQUIRED_FIELDS_STR)

        if issue_data:
            logger.info(f"Successfully retrieved issue details for {issue_key}.")
            return json.dumps(issue_data)
        else:
            logger.warning(f"Jira API returned no data for issue {issue_key}.")
            return json.dumps(
                {"error": f"Issue '{issue_key}' not found or no data returned."}
            )

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

        return json.dumps({"error": error_message})
