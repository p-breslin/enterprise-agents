import os
import logging
from utils_agno import get_jira_client, load_config, save_yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

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
        logger.error("Failed to initialize Jira client.")
        return False

    try:
        all_fields_list = jira.fields()
        logger.info(f"Successfully fetched {len(all_fields_list)} fields.")
    except Exception as e:
        logger.error(f"Failed to fetch fields from Jira: {e}", exc_info=True)
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
            logger.warning(f"Skipping field due to missing name or ID: {field}")

    if not save_yaml(ALL_FIELDS_FILE_PATH, all_field_map):
        return False  # Stop if we can't save the first file

    # --- Create and save selected field mappings ---
    selected_mappings = {}
    missing_mappings = []
    logger.info("Attempting to map canonical names to actual field IDs...")

    selected_ids = load_config(FIELD_IDS_FILENAME)
    for canonical_name, common_jira_name in selected_ids.items():
        # Try case-insensitive lookup using the common name
        actual_field_id = field_name_to_id_lower.get(common_jira_name.lower())

        if actual_field_id:
            selected_mappings[canonical_name] = actual_field_id
            logger.info(
                f"Mapped '{canonical_name}' -> '{actual_field_id}' (found via '{common_jira_name}')"
            )
        else:
            # Handle special cases or known variations if needed
            # Example: If 'Issue key' wasn't found, maybe try 'key'
            if canonical_name == "key" and "key" in field_name_to_id_lower:
                selected_mappings[canonical_name] = field_name_to_id_lower["key"]
                logger.info(
                    f"Mapped '{canonical_name}' -> '{field_name_to_id_lower['key']}' (found via alternative 'key')"
                )
            # Add more specific fallbacks if necessary...
            else:
                logger.warning(
                    f"Could not find Jira field matching common name '{common_jira_name}' for canonical name '{canonical_name}'. This mapping will be missing."
                )
                missing_mappings.append(canonical_name)

    if missing_mappings:
        print("WARNING: Could not map the following required fields:")
        for name in missing_mappings:
            print(f"- {name} (Tried to find: '{selected_ids.get(name)}')")

    if not save_yaml(SELECTED_FIELDS_FILE_PATH, selected_mappings):
        return False

    logger.info("Both configuration files generated successfully.")
    return True


# --- Main Execution ---
if __name__ == "__main__":
    if generate_field_configs():
        logger.info("Field configuration generation process completed.")
    else:
        logger.error("Field configuration generation process failed.")
