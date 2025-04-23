import json
import logging
from agno.tools import tool
from integrations.jira_client import get_atlassian_client

log = logging.getLogger(__name__)


# --- Jira Tool Function: Search Issues from Epics ---
@tool()
def jira_get_epic_issues(epic_key: str) -> str:
    """
    Tool Purpose:
        Retrieves Jira issue keys belonging to a specific Epic using the atlassian-python-api library, which targets the /rest/agile/1.0/epic/{epicIdOrKey}/issue endpoint. Requests ONLY the issue keys for efficiency.

    Args:
        epic_key (str): The key of the Epic issue (e.g., 'PROJ-123'). REQUIRED.

    Returns:
        str: A JSON string representation of a list of issue objects, where each object contains only the 'key'. Example: '[{"key": "PROJ-456"}, {"key": "PROJ-457"}]'.
            - Returns '[]' if no issues are found.
            - Returns '[{"error": "message"}]' if an error occurs.
    """
    jira = get_atlassian_client()
    if not jira:
        return json.dumps([{"error": "Failed to initialize Jira client."}])

    try:
        log.debug(f"Calling jira.epic_issues for epic '{epic_key}'")
        results = jira.epic_issues(
            epic=epic_key,
            fields=["key"],  # Request only the key (story_key)
        )

        # Process results
        if isinstance(results, dict) and "issues" in results:
            issues_list = results.get("issues", [])
            issue_keys = [
                {"key": issue.get("key")} for issue in issues_list if issue.get("key")
            ]
            log.info(f"Found {len(issue_keys)} issue keys for Epic {epic_key}.")
            return json.dumps(issue_keys)
        elif isinstance(results, list):  # If it directly returns a list
            issue_keys = [
                {"key": issue.get("key")} for issue in results if issue.get("key")
            ]
            log.info(f"Found {len(issue_keys)} issue keys for Epic {epic_key}.")
            return json.dumps(issue_keys)
        else:
            log.warning(
                f"No issues found or unexpected result format for Epic {epic_key}. Result: {results}"
            )
            return json.dumps([])

    except Exception as e:
        log.error(f"Error during search for Epic {epic_key}: {e}", exc_info=True)
        error_message = (
            f"An error occurred while searching Jira for epic '{epic_key}': {str(e)}"
        )
        if "does not exist" in str(e):
            error_message = f"Epic '{epic_key}' not found or call failed."
        return json.dumps([{"error": error_message}])
