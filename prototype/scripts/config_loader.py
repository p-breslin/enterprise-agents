import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Configure logging for this module
logger = logging.getLogger(__name__)

# Define expected ID keys for processing lists into dictionaries
CFG_LIST_TO_DICT_KEYS: Dict[str, str] = {
    "agent_config": "agent_id",
    "agent_workflows": "workflow_id",
    "analysis_tasks": "task_type",
    "entity_types": "name",
    "prompt_templates": "template_id",
    "relationship_types": "name",
    "system_prompts": "system_prompt_id",
}


class ConfigLoader:
    """
    Loads and processes YAML configuration files from a specified directory.

    Attributes:
        cfg_dir (Path): The directory containing configuration files.
        cfgs (Dict[str, Any]): A dictionary holding the loaded and processed configuration data, keyed by filename stem.
    """

    def __init__(self, cfg_dir: str = "prototype/configs"):
        """
        Initializes the ConfigLoader, loads, and processes all YAML files.

        Args:
            cfg_dir (str): The path to the directory containing .yaml files. Defaults to "prototype/configs".

        Raises:
            FileNotFoundError: If the specified cfg_dir does not exist.
        """
        self.cfg_dir = Path(cfg_dir)
        self.cfgs: Dict[str, Any] = {}

        if not self.cfg_dir.is_dir():
            msg = f"Config directory not found: {self.cfg_dir.resolve()}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        logger.info(
            f"Initializing ConfigLoader for directory: {self.cfg_dir.resolve()}"
        )
        self._load_all_configs()
        self._process_configs()
        logger.info("ConfigLoader initialization complete.")

    def _load_all_configs(self) -> None:
        """
        Discovers and loads all .yaml files from the config directory.
        Handles potential YAML parsing errors or file access issues.
        """
        logger.debug(f"Scanning for YAML files in {self.cfg_dir}...")
        yaml_files_found = 0
        for file_path in self.cfg_dir.glob("*.yaml"):
            yaml_files_found += 1
            cfg_key: str = file_path.stem  # filename without its extension

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    loaded_data = yaml.safe_load(f)

                    if loaded_data is not None:
                        self.cfgs[cfg_key] = loaded_data
                        logger.debug(f"Successfully loaded '{file_path.name}'")
                    else:
                        logger.warning(
                            f"Config file '{file_path.name}' is empty or contains only comments. Skipping."
                        )

            except yaml.YAMLError as e:
                logger.error(
                    f"Error parsing YAML file '{file_path.name}': {e}", exc_info=True
                )
            except IOError as e:
                logger.error(
                    f"Error reading file '{file_path.name}': {e}", exc_info=True
                )
            except Exception as e:
                logger.error(
                    f"Error loading '{file_path.name}': {e}",
                    exc_info=True,
                )

        if yaml_files_found == 0:
            logger.warning(
                f"No YAML files found in the configuration directory: {self.cfg_dir}"
            )
        else:
            logger.info(f"Found and attempted to load {yaml_files_found} YAML file(s).")

    def _process_configs(self) -> None:
        """
        Centralizes the logic for converting lists into dictionaries keyed by their unique ID. Uses the CFG_LIST_TO_DICT_KEYS mapping to determine the ID field for each config type.
        """
        logger.debug("Processing loaded configurations...")
        for cfg_key, id_field in CFG_LIST_TO_DICT_KEYS.items():
            if cfg_key in self.cfgs:
                original_data = self.cfgs[cfg_key]

                if isinstance(original_data, list):
                    processed_dict: Dict[str, Any] = {}
                    items_processed = 0
                    items_skipped = 0

                    for item in original_data:
                        if isinstance(item, dict):
                            item_id = item.get(id_field)

                            if item_id is not None:
                                if item_id in processed_dict:
                                    # Duplicate check
                                    logger.warning(
                                        f"Duplicate ID '{item_id}' found in '{cfg_key}'. "
                                        f"Overwriting previous entry. Check '{cfg_key}.yaml'."
                                    )

                                # Ensure ID is string key
                                processed_dict[str(item_id)] = item
                                items_processed += 1
                            else:
                                logger.warning(
                                    f"Item in '{cfg_key}' is missing the expected ID field '{id_field}'. "
                                    f"Skipping item: {item}"
                                )
                                items_skipped += 1
                        else:
                            logger.warning(
                                f"Item in '{cfg_key}' is not a dictionary. Skipping item: {item}"
                            )
                            items_skipped += 1

                    # Only update if processing occurred
                    if items_processed > 0 or items_skipped > 0:
                        self.cfgs[cfg_key] = processed_dict
                        logger.debug(
                            f"Processed '{cfg_key}': {items_processed} items mapped by '{id_field}', "
                            f"{items_skipped} items skipped."
                        )

                # We will allow configurations that aren't lists
                elif original_data is not None:
                    logger.debug(
                        f"Configuration '{cfg_key}' is not a list, skipping list-to-dict processing."
                    )
            else:
                logger.debug(
                    f"Configuration key '{cfg_key}' not found in loaded cfgs, skipping processing."
                )

    def get_config(self, key: str) -> Optional[Any]:
        """
        Retrieves the configuration data associated with the given key.

        Args:
            key (str): The key for the desired configuration.

        Returns:
            Optional[Any]: The loaded configuration data (could be a dict, list, etc.) or None if the key is not found.
        """
        config_data = self.cfgs.get(key)
        if config_data is None:
            logger.warning(f"Configuration key '{key}' not found.")
        return config_data

    def get_all_configs(self) -> Dict[str, Any]:
        """
        Returns the entire dictionary of loaded configurations.

        Returns:
            Dict[str, Any]: All loaded configurations.
        """
        return self.cfgs


# Test usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s - %(message)s",
    )

    try:
        loader = ConfigLoader(cfg_dir="prototype/configs")

        # Get specific configurations
        agent_config = loader.get_config("agent_config")
        prompts = loader.get_config("prompt_templates")
        workflows = loader.get_config("agent_workflows")

        # Print structure of a processed config
        if agent_config:
            logger.info("Sample Agent Config (Processed):")

            # Print first item if available
            first_agent_id = next(iter(agent_config), None)
            if first_agent_id:
                logger.info(
                    f"Agent ID '{first_agent_id}': {agent_config[first_agent_id]}"
                )
            else:
                logger.info("Agent config is empty after processing.")

        if prompts:
            logger.info(f"\nLoaded {len(prompts)} prompt templates.")

        if workflows:
            logger.info(f"\nLoaded {len(workflows)} workflows.")
            logger.info(
                f"Workflow 'INITIAL_ANALYSIS': {workflows.get('INITIAL_ANALYSIS')}"
            )

    except FileNotFoundError:
        logger.error("Failed to initialize ConfigLoader due to missing directory.")
    except Exception as e:
        logger.error(
            f"An error occurred during ConfigLoader demonstration: {e}", exc_info=True
        )
