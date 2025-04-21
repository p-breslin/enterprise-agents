import json
import logging
from agno.tools import tool
from typing import List
from utils_agno import get_jira_client

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# --- Jira Tool Function: Searches Jira ---
@tool()
def jira_search(jql: str, fields: List[str], limit: int = 50) -> str:
    """
    Tool Purpose:
        Executes a JQL query against Jira and returns matching issues with specified fields as a JSON string.

    This tool performs a search based on the provided JQL string, limiting the results and requesting only the specified fields for efficiency. It returns the raw list of issue data dictionaries directly from the Jira API.

    Args:
        jql (str): The JQL query string to execute. REQUIRED.
        fields (List[str]): A list of field names to retrieve for each issue (e.g., ["key", "summary", "status", "project"]). REQUIRED.
        limit (int): The maximum number of issues to return. Defaults to 50.

    Returns:
        str: A JSON string representation of the list of issue dictionaries.
            - Returns a JSON string of an empty list '[]' if no issues match.
            - Returns a JSON string of a list containing a single error object(e.g., '[{"error": "message"}]') if an error occurs.
    """
    logger.info(
        f"Tool 'jira_search' called with JQL: '{jql}', fields: {fields}, limit: {limit}"
    )
    jira = get_jira_client()
    if not jira:
        return json.dumps([{"error": "Jira client initialization failed."}])

    # Prepare fields argument for the API call
    fields_list = fields if fields else ["*navigable"]

    try:
        logger.info(
            f"Executing JQL via enhanced_search_issues: {jql} with fields: {fields_list}, maxResults: {limit}"
        )

        # Use enhanced_search_issues from Jira API
        issues_data = jira.enhanced_search_issues(
            jql_str=jql, fields=fields_list, maxResults=limit, json_result=True
        )

        if issues_data and "issues" in issues_data:
            issues = issues_data["issues"]
            logger.info(f"JQL search successful: {len(issues)} issues.")
            return json.dumps(issues)  # Return the raw list directly
        else:
            logger.warning(f"No issues found for JQL: {jql}")
            return json.dumps([])  # Return empty list if no issues found

    except Exception as e:
        logger.error(f"Error during Jira enhanced_search_issues: {e}", exc_info=True)
        error_message = f"Error occurred while executing JQL '{jql}': {str(e)}"

        # Check for common errors if possible (e.g., invalid JQL, permissions)
        if "Invalid JQL" in str(e):
            error_message = f"Invalid JQL query: {jql}. Error: {str(e)}"
        elif "401" in str(e) or "Unauthorized" in str(e):
            error_message = "Authentification failed. Check Jira permissions."
        elif "403" in str(e) or "Forbidden" in str(e):
            error_message = f"Permission denied for JQL search: {jql}"

        return json.dumps([{"error": error_message}])
