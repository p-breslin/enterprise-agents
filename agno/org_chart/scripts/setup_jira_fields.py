import os
import logging
from utils.helpers import get_jira_client, load_config, save_yaml
from utils.logging_setup import setup_logging

setup_logging()
log = logging.getLogger(__name__)

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(__file__)
CONFIG_DIR = os.path.join(SCRIPT_DIR, "configs")

FIELD_IDS_FILENAME = "field_ids"
ALL_FIELDS_FILENAME = "all_jira_fields.yaml"
SELECTED_FIELDS_FILENAME = "selected_jira_fields.yaml"

FIELD_IDS_FILE_PATH = os.path.join(SCRIPT_DIR, f"{FIELD_IDS_FILENAME}.yaml")
ALL_FIELDS_FILE_PATH = os.path.join(CONFIG_DIR, ALL_FIELDS_FILENAME)
SELECTED_FIELDS_FILE_PATH = os.path.join(CONFIG_DIR, SELECTED_FIELDS_FILENAME)

"""
Define the CANONICAL names your application uses internally, mapped to the COMMON/DEFAULT names usually found in Jira. The script will try to find the actual ID based on the common name.
"""


# --- Main Function ---
def generate_field_configs():
    """
    Fetches all fields and generates both the full field mapping and the chosen field mappings (determined by field_ids.yaml config).
    """
    jira = get_jira_client()
    if not jira:
        log.error("Failed to initialize Jira client.")
        return False

    try:
        all_fields_list = jira.fields()
        log.info(f"Successfully fetched {len(all_fields_list)} fields.")
    except Exception as e:
        log.error(f"Failed to fetch fields from Jira: {e}", exc_info=True)
        return False

    # --- Create and save ALL field mappings ---
    all_field_map = {}
    field_name_to_id_lower = {}  # For case-insensitive lookup later

    for field in all_fields_list:
        field_id = field.get("id")
        field_name = field.get("name")

        if field_id and field_name:
            all_field_map[field_name] = field_id
            field_name_to_id_lower[field_name.lower()] = field_id
        else:
            log.warning(f"Skipping field due to missing name or ID: {field}")

    if not save_yaml(ALL_FIELDS_FILE_PATH, all_field_map):
        return False  # Stop if we can't save the first file

    # --- Create and save selected field mappings ---
    selected_mappings = {}
    missing_mappings = []
    log.info("Attempting to map internal names to actual field IDs...")

    selected_ids = load_config(FIELD_IDS_FILENAME)
    for internal_name, common_jira_name in selected_ids.items():
        # Try case-insensitive lookup using the common name
        actual_field_id = field_name_to_id_lower.get(common_jira_name.lower())

        if actual_field_id:
            selected_mappings[internal_name] = actual_field_id
            log.info(
                f"Mapped '{internal_name}' -> '{actual_field_id}' (found via '{common_jira_name}')"
            )
        else:
            # Handle special cases or known variations if needed
            # Example: If 'Issue key' wasn't found, maybe try 'key'
            if internal_name == "key" and "key" in field_name_to_id_lower:
                selected_mappings[internal_name] = field_name_to_id_lower["key"]
                log.info(
                    f"Mapped '{internal_name}' -> '{field_name_to_id_lower['key']}' (found via alternative 'key')"
                )
            # Add more specific fallbacks if necessary...
            else:
                log.warning(
                    f"Could not find Jira field matching common name '{common_jira_name}' for internal name '{internal_name}'. This mapping will be missing."
                )
                missing_mappings.append(internal_name)

    if missing_mappings:
        print("WARNING: Could not map the following required fields:")
        for name in missing_mappings:
            print(f"- {name} (Tried to find: '{selected_ids.get(name)}')")

    if not save_yaml(SELECTED_FIELDS_FILE_PATH, selected_mappings):
        return False

    log.info("Both configuration files generated successfully.")
    return True


# --- Main Execution ---
if __name__ == "__main__":
    if generate_field_configs():
        log.info("Field configuration generation process completed.")
    else:
        log.error("Field configuration generation process failed.")
