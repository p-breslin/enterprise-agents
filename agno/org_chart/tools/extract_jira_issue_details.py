import json
import logging
from typing import List, Dict, Any, Optional

log = logging.getLogger(__name__)


def _safe_get(data: Optional[Dict], key: str, default: Any = None) -> Any:
    """
    Helper function to safely get a value from a dictionary, returning default if data is None or key is missing.
    """
    return data.get(key, default) if isinstance(data, dict) else default


def _simplify_jira_field(internal_name: str, jira_id: str, raw_value: Any) -> Any:
    """
    Extracts a simplified value from a raw Jira field based on common patterns.
    """
    if raw_value is None:
        return None

    # Fields that are typically direct strings or dates (10038 = story points)
    if jira_id in [
        "summary",
        "description",
        "created",
        "updated",
        "resolutiondate",
        "customfield_10038",
    ]:
        return raw_value

    # Fields with the 'displayName' sub-key
    if jira_id in ["assignee", "reporter"]:
        return _safe_get(raw_value, "displayName")

    # Fields with the 'name' sub-key
    elif jira_id in ["status", "priority", "issuetype", "resolution"]:
        return _safe_get(raw_value, "name")

    # Fields with the 'key' sub-key
    elif jira_id in ["project", "parent"]:
        return _safe_get(raw_value, "key")

    # Fields with the 'value' sub-key (Issue Size, Team Name)
    elif jira_id in ["customfield_10124", "customfield_10162"]:
        return _safe_get(raw_value, "value")

    # Sprint (List of sprints) - extract info from the first sprint in the list
    elif jira_id == "customfield_10008":
        if isinstance(raw_value, list) and raw_value:
            return _safe_get(raw_value[0], "name")  # also ID, state, dates
        return None

    # --- Fallback for unhandled fields ---
    log.warning(
        f"Unhandled field structure for internal_name='{internal_name}' "
        f"(jira_id='{jira_id}'). Type: {type(raw_value)}. Returning raw value as string."
    )
    return str(raw_value)


def extract_details(
    raw_issue_list_json: str, field_mappings: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Processes a list of raw Jira issue dictionaries (from jira.issue().raw or errors) and extracts specified fields into a simplified format using internal names.

    Args:
        raw_issue_list_json (str): A JSON string containing a list of raw issue data dictionaries or error dictionaries.
        field_mappings (Dict[str, str]): A dictionary mapping internal application field names (keys) to their corresponding Jira field IDs (values).

    Returns:
        List[Dict[str, Any]]: A list of dictionaries. Each dictionary represents either:
            - Processed issue with internal names as keys and simplified values.
            - An error object if the original item was an error.
    """
    try:
        raw_issue_list = json.loads(raw_issue_list_json)
        if not isinstance(raw_issue_list, list):
            log.error("Input JSON is not a list.")
            return [{"error": "Invalid input format: Expected JSON list."}]
    except json.JSONDecodeError as e:
        log.error(f"Failed to decode input JSON string: {e}")
        return [{"error": f"Invalid JSON input: {e}"}]
    except Exception as e:
        log.error(f"Unexpected error loading JSON data: {e}", exc_info=True)
        return [{"error": f"Unexpected error loading JSON: {str(e)}"}]

    processed_results: List[Dict[str, Any]] = []

    for raw_issue in raw_issue_list:
        if not isinstance(raw_issue, dict):
            log.warning(
                f"Skipping invalid item in list (not a dictionary): {raw_issue}"
            )
            processed_results.append(
                {
                    "error": "Invalid item in list: not a dictionary.",
                    "item_value": str(raw_issue),
                }
            )
            continue

        # Pass through error objects directly
        if "error" in raw_issue:
            processed_results.append(raw_issue)
            continue

        # Process a successfully fetched issue
        processed_issue: Dict[str, Any] = {}
        fields_data = raw_issue.get("fields")  # main container for field values

        # --- Handle Top-Level Fields FIRST ---
        story_key = raw_issue.get("key")
        if story_key:
            processed_issue["story_key"] = story_key
        else:
            log.warning(
                "Issue data missing top-level 'key'. Cannot set 'story_key'. Skipping issue."
            )
            processed_results.append(
                {
                    "error": "Missing key in raw issue data",
                    "raw_id": raw_issue.get("id"),
                }
            )
            continue

        # Check if fields_data is valid before proceeding
        if not isinstance(fields_data, dict):
            log.warning(f"Issue {story_key} missing 'fields' dict.")
            processed_issue["warning"] = "Missing 'fields' data in raw response"
            processed_results.append(processed_issue)
            continue

        # Iterate through mappings for fields WITHIN the 'fields' dict
        for internal_name, jira_id in field_mappings.items():
            if internal_name in ["key", "id"]:
                # Skipping key and unwanted values (like ID)
                continue

            # Process the selected fields
            raw_value = fields_data.get(jira_id)
            processed_issue[internal_name] = _simplify_jira_field(
                internal_name, jira_id, raw_value
            )

        processed_results.append(processed_issue)

    return processed_results
