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
    Tool Purpose:
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


# --- Jira Tool Function: Get Batch Issues using enhanced_search_issues ---
def jira_get_issue_batch(
    issue_keys: List[str], max_results_per_batch: int = 100
) -> str:
    """
    Tool Purpose:
        Retrieves SPECIFIC details for multiple Jira issues using enhanced_search_issues from the Jira API. Fetches only necessary fields for a list of issue keys in potentially fewer requests.

    Args:
        issue_keys (List[str]): A list of Jira issue keys to retrieve (e.g., ['PROJ-1', 'PROJ-2']). REQUIRED.
        max_results_per_batch (int): Max results per underlying API call (used for potential pagination if needed, though typically fetching by key won't require multiple pages unless list is huge). Defaults to 100.

    Returns:
        str: A JSON string representation of a list of dictionaries, each containing the requested fields for the found issues.
            - Returns '[]' if no issues are found.
            - Returns '[{"error": "message"}]' if a connection or major API error occurs.
    """
    if not issue_keys:
        logger.warning(
            "Tool 'jira_get_issue_batch' called with empty issue_keys list."
        )
        return json.dumps([])

    # Limit the number of keys per request if necessary
    # (JQL length might be the real limit)
    if len(issue_keys) > max_results_per_batch:
        logger.warning(
            f"Requested {len(issue_keys)} keys, but batch limit is {max_results_per_batch}. Fetching first {max_results_per_batch}."
        )
        # Note: For simplicity, this implementation doesn't handle fetching keys beyond the first batch limit
        # A production system might need to loop and make multiple batch calls if thousands of keys were passed!
        keys_to_fetch = issue_keys[:max_results_per_batch]
    else:
        keys_to_fetch = issue_keys

    logger.info(f"Tool 'jira_get_issue_batch' called for {len(keys_to_fetch)} keys.")
    jira = get_jira_client()
    if not jira:
        return json.dumps([{"error": "Jira client initialization failed."}])

    # Format keys for JQL "in" clause: "KEY-1","KEY-2",...
    formatted_keys = ",".join([f'"{key}"' for key in keys_to_fetch])
    jql_query = f"key in ({formatted_keys})"

    logger.info(
        f"Executing Batch JQL via enhanced_search_issues: {jql_query} (MaxResults: {max_results_per_batch})"
    )
    logger.debug(f"Requesting fields: {_REQUIRED_FIELDS_STR}")

    try:
        # Use enhanced_search_issues with json_result=True
        response_dict = jira.enhanced_search_issues(
            jql_str=jql_query,
            fields=_REQUIRED_ISSUE_FIELDS,  # Pass the list directly
            maxResults=max_results_per_batch,
            json_result=True,  # Get the raw dictionary back
        )

        # The response dictionary contains the 'issues' list
        if response_dict and "issues" in response_dict:
            found_issues = response_dict["issues"]
            logger.info(
                f"Batch search successful. Found {len(found_issues)} issues out of {len(keys_to_fetch)} requested."
            )
            return json.dumps(found_issues)  # Dump the list of issues found
        else:
            logger.warning(
                f"No issues found or unexpected response format for batch JQL: {jql_query}. Response: {response_dict}"
            )
            return json.dumps([])

    except Exception as e:
        logger.error(f"Error during Jira batch search: {e}", exc_info=True)
        error_message = f"An error occurred while executing batch search for keys {keys_to_fetch[:5]}...: {str(e)}"
        return json.dumps([{"error": error_message}])
