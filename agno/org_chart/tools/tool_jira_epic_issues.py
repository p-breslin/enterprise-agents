import json
import logging
from agno.tools import tool
from utils_agno import get_jira_client

logging.basicConfig(
    level=logging.INFO, format="%(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Jira Tool Function: Search Issues from Epics ---
@tool()
def jira_get_epic_issues(epic_key: str, max_results: int = 50) -> str:
    """
    Tool Purpose:
        Searches for Jira issue keys belonging to a specific Epic using JQL via enhanced_search_issues. Queries Jira for issues linked to the Epic via 'parent' field and returns ONLY the issue keys as a JSON string.

    Args:
        epic_key (str): The key of the Epic issue (e.g., 'PROJ-123'). REQUIRED.
        max_results (int): Maximum number of issues to return. Defaults to 50.

    Returns:
        str: A JSON string representation of a list of issue objects, where each object contains only the 'key'. Example: '[{"key": "PROJ-456"}, {"key": "PROJ-457"}]'.
            - Returns '[]' if no issues are found.
            - Returns '[{"error": "message"}]' if an error occurs.
    """
    logger.info(
        f"Tool 'jira_get_epic_issues' called for Epic: {epic_key} (limit: {max_results})"
    )
    jira = get_jira_client()
    if not jira:
        return json.dumps([{"error": "Failed to initialize Jira client."}])

    # JQL query targeting 'parent' field
    jql_query = f'parent = "{epic_key}" ORDER BY created DESC'
    logger.info(f"Executing JQL: {jql_query}")

    try:
        # Request ONLY the necessary fields for efficiency
        issues = jira.enhanced_search_issues(
            jql_str=jql_query,
            fields=["key"],  # Critical for efficiency
            maxResults=max_results,
            json_result=True,
        )

        # Extract just the necessary part in-case more data is returned
        if issues and "issues" in issues:
            issue_keys = [
                {"key": issue.get("key")}
                for issue in issues["issues"]
                if issue.get("key")  # Ensure key exists
            ]
            logger.info(f"Found {len(issue_keys)} issue keys for Epic {epic_key}.")
            return json.dumps(issue_keys)
        else:
            logger.info(f"No issues found for Epic {epic_key} with JQL: {jql_query}")
            return json.dumps([])

    except Exception as e:
        logger.error(
            f"Error during Jira JQL search for Epic {epic_key}: {e}", exc_info=True
        )
        error_message = (
            f"An error occurred while searching Jira for epic '{epic_key}': {str(e)}"
        )
        if "does not exist" in str(e):
            error_message = f"Epic '{epic_key}' not found or JQL query failed."
        return json.dumps([{"error": error_message}])
