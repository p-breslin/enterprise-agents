import json
import logging
from typing import List
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


# --- Jira Tool Function: Get Multiple Issues (Batch) ---
@tool()
def jira_get_issues_batch(
    issue_keys: List[str], max_results_per_batch: int = 100
) -> str:
    """
    Retrieves SPECIFIC details for multiple Jira issues using a batch JQL query.

    Fetches only necessary fields for a list of issue keys in a single request to improve efficiency and reduce network latency/API calls.

    Args:
        issue_keys (List[str]): A list of Jira issue keys to retrieve (e.g., ['PROJ-1', 'PROJ-2']). REQUIRED.
        max_results_per_batch (int): Jira often limits JQL results per query. This sets that limit. Defaults to 100.

    Returns:
        str: A JSON string representation of a list of dictionaries, each containing the requested fields for the found issues. Issues not found or inaccessible will be omitted from the result list.
        - Returns '[]' if no issues are found.
        - Returns '[{"error": "message"}]' for a connection or major API error.
        - Note: Individual key errors (like one key not found) are not typically returned as errors, the query just returns the valid results.
    """
    if not issue_keys:
        logger.warning(
            "Tool 'jira_get_issues_batch' called with empty issue_keys list."
        )
        return json.dumps([])

    logger.info(f"Tool 'jira_get_issues_batch' called for {len(issue_keys)} keys.")
    jira = get_jira_client()
    if not jira:
        return json.dumps([{"error": "Jira client initialization failed."}])

    # Format keys for JQL "in" clause: "KEY-1","KEY-2",...
    formatted_keys = ",".join([f'"{key}"' for key in issue_keys])

    # Construct JQL query
    jql_query = f"key in ({formatted_keys})"

    # Limit results - important for large lists
    limit = min(len(issue_keys), max_results_per_batch)

    logger.info(f"Executing Batch JQL: {jql_query} (Limit: {limit})")
    logger.debug(f"Requesting fields: {_REQUIRED_FIELDS_STR}")

    try:
        # Use JQL for specific fields only
        issues_data = jira.jql(
            jql_query,
            limit=limit,
            fields=_REQUIRED_FIELDS_STR,
        )

        if issues_data and "issues" in issues_data:
            raw_issues = issues_data["issues"]
            logger.info(
                f"Batch JQL successful. Found {len(raw_issues)} issues out of {len(issue_keys)} requested."
            )
            # Return the list of found issues
            return json.dumps(raw_issues)
        else:
            logger.warning(f"No issues found for batch JQL: {jql_query}")
            return json.dumps([])

    except Exception as e:
        logger.error(f"Error during Jira batch JQL search: {e}", exc_info=True)
        error_message = f"An error occurred while executing batch JQL for keys {issue_keys[:5]}...: {str(e)}"
        return json.dumps([{"error": error_message}])
