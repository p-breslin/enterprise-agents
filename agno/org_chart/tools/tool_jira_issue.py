import json
import logging
from typing import List, Dict, Any
from agno.tools import tool
from utils_agno import get_jira_client, load_config
from tools.extract_jira_issue_details import extract_details

logging.basicConfig(
    level=logging.DEBUG, format="%(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Define the specific fields to be returned ---
field_mappings = load_config("selected_jira_fields")
_REQUIRED_FIELDS_STR = ",".join(field_mappings.values())


# --- Jira Tool Function: Get Single Issue (e.g. Story from Epic) ---
@tool()
def jira_get_issue(issue_key: str) -> str:
    """
    Tool Purpose:
        Retrieves the SPECIFIC details of a single Jira issue by its key as a JSON string. Uses the jira.issue() method and requests only necessary fields.

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
        issue_object = jira.issue(issue_key, fields=_REQUIRED_FIELDS_STR)

        # Complete dictionary structure is stored under the .raw attribute
        if issue_object and hasattr(issue_object, "raw"):
            logger.info(f"Successfully retrieved issue details for {issue_key}.")
            return json.dumps(issue_object.raw)
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


# --- Jira Tool Function: Get mutiple Issues using single jira.issue() calls ---
@tool
def jira_get_issue_loop(issue_keys: List[str]) -> str:
    """
    Tool Purpose:
        Retrieves SPECIFIC details for multiple Jira issues by fetching EACH issue individually using jira.issue().

    Args:
        issue_keys (List[str]): A list of Jira issue keys to retrieve (e.g., ['PROJ-1', 'PROJ-2']). REQUIRED.

    Returns:
        str: A JSON string representation of a list of dictionaries, each containing the full issue structure (including requested fields) for successfully found issues. Issues that failed to fetch (e.g., not found, permission error) will be omitted or could optionally be represented by an error object.
            - Returns '[]' if the input list was empty or no issues could be successfully fetched. May contain a mix of successful issue data and error objects if desired (currently omits errors).
    """
    if not issue_keys:
        logger.warning("Tool 'jira_get_issue_loop' called with empty issue_keys list.")
        return json.dumps([])

    logger.info(
        f"Tool 'jira_get_issue_loop' called for {len(issue_keys)} keys (fetching individually)."
    )
    jira = get_jira_client()
    if not jira:
        logger.error("jira_get_issue_loop: Jira client initialization failed.")
        return json.dumps([{"error": "Jira client initialization failed."}])

    fetched_raw_issues: List[Dict[str, Any]] = []
    fetch_errors: List[Dict[str, Any]] = []

    logger.debug(f"Fetching details individually for fields: {_REQUIRED_FIELDS_STR}")

    for key in issue_keys:
        try:
            logger.debug(f"Fetching issue: {key}")
            issue_object = jira.issue(key, fields=_REQUIRED_FIELDS_STR)

            if issue_object and hasattr(issue_object, "raw"):
                fetched_raw_issues.append(issue_object.raw)
                logger.debug(f"Successfully fetched {key}.")
            else:
                logger.warning(
                    f"jira.issue({key}) returned None or no raw data, skipping."
                )
                fetch_errors.append(
                    {"error": f"No data returned for issue '{key}'.", "failed_key": key}
                )
        except Exception as e:
            logger.error(f"Unexpected error fetching issue {key}: {e}", exc_info=True)
            fetch_errors.append(
                {
                    "error": f"Unexpected error for issue '{key}': {str(e)}",
                    "failed_key": key,
                }
            )

    # Decide what to return: only successes, or successes + errors? Not sure
    if fetch_errors:
        logger.warning(
            f"Encountered {len(fetch_errors)} errors while fetching {len(issue_keys)} issues individually."
        )

    logger.info(
        f"Finished fetching individually. Successfully retrieved data for {len(fetched_raw_issues)} out of {len(issue_keys)} issues."
    )

    # Process the list of raw dictionaries to extract relevant info
    data = extract_details(json.dumps(fetched_raw_issues), field_mappings)
    return json.dumps(data)


# --- Jira Tool Function: Get Batch Issues using enhanced_search_issues ---
@tool
def jira_get_issue_batch(
    issue_keys: List[str], max_results_per_batch: int = 100
) -> str:
    """
    THIS IS BROKEN! both the search_issues and enhanced_search_issues methods omit the fields parameter when making the GET requests. Means that only Issue IDs are returned! Bug with jira-python wrapper.

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
        logger.warning("Tool 'jira_get_issue_batch' called with empty issue_keys list.")
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
            fields=[_REQUIRED_FIELDS_STR],  # Pass the list directly
            maxResults=max_results_per_batch,
            json_result=True,  # Get the raw dictionary back
        )

        # The response dictionary contains the 'issues' list
        if response_dict and "issues" in response_dict:
            found_issues = response_dict["issues"]
            logger.info(
                f"Batch search successful. Found {len(found_issues)} issues out of {len(keys_to_fetch)} requested."
            )
            if found_issues:
                logger.debug(
                    f"First found issue structure: {json.dumps(found_issues[0], indent=2)}"
                )
            else:
                logger.debug("Found issues list is empty.")
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
