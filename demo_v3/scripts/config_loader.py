import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

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
    "output_schemas": "schema_id",
}


class ConfigLoader:
    """
    Loads and processes YAML configuration files into dictionaries, accessible by config name.

    Notes:
        - Transforms list-based configs into dicts using unique IDs.
    """

    def __init__(self, cfg_dir: str = "configs"):
        self.cfg_dir = Path(cfg_dir)
        self.cfgs: Dict[str, Any] = {}

        if not self.cfg_dir.is_dir():
            raise FileNotFoundError(
                f"Config directory not found: {self.cfg_dir.resolve()}"
            )

        logger.info(
            f"Initializing ConfigLoader for directory: {self.cfg_dir.resolve()}"
        )
        self._load_all_configs()
        self._process_configs()
        logger.info("ConfigLoader initialization complete.")

    def _load_all_configs(self) -> None:
        """
        Purpose:
            Loads all .yaml files from the config directory into memory.
        Notes:
            Stores them in self.cfgs keyed by the file stem (filename without extension).
        """
        logger.debug(f"Scanning for YAML files in {self.cfg_dir}...")

        for file in self.cfg_dir.glob("*.yaml"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data:
                    self.cfgs[file.stem] = data  # filename without extension
                    logger.debug(f"Loaded config: {file.name}")
                else:
                    logger.warning(f"Empty or comment-only config: {file.name}")

            except Exception as e:
                logger.error(f"Failed to load config '{file.name}': {e}", exc_info=True)

    def _process_configs(self) -> None:
        """
        Purpose:
            Converts list configs to dicts keyed by their unique ID fields.
        Notes:
            Uses CFG_LIST_TO_DICT_KEYS mapping to determine the ID field.
        """
        logger.debug("Processing loaded configurations...")
        for cfg_key, id_field in CFG_LIST_TO_DICT_KEYS.items():
            items = self.cfgs.get(cfg_key)

            if not isinstance(items, list):
                continue

            processed = {}
            for item in items:
                if not isinstance(item, dict):
                    logger.warning(f"Non-dict entry in '{cfg_key}': {item}")
                    continue

                item_id = item.get(id_field)
                if not item_id:
                    logger.warning(f"Missing ID '{id_field}' in '{cfg_key}': {item}")
                    continue

                if item_id in processed:
                    logger.warning(
                        f"Duplicate '{item_id}' in '{cfg_key}', overwriting."
                    )

                # Ensure ID is string key
                processed[str(item_id)] = item

            self.cfgs[cfg_key] = processed
            logger.debug(f"Processed {cfg_key} to dict with {len(processed)} items.")

    def get_config(self, key: str) -> Optional[Any]:
        """
        Retrieves the configuration data associated with the given key.
        """
        config_data = self.cfgs.get(key)
        if config_data is None:
            logger.warning(f"Configuration key '{key}' not found.")
        return config_data

    def get_all_configs(self) -> Dict[str, Any]:
        """
        Returns the entire dictionary of loaded configurations.
        """
        return self.cfgs

    def load_workflow_sequence(self, workflow_id: str) -> List[str]:
        """
        Purpose:
            Retrieves + parses agent sequence string for a given workflow ID.
        Notes:
            - Returns an ordered list of agent IDs. Returns an empty list if the ID is invalid or improperly formatted.
        """
        # agent_workflows is processed into a dict with workflow_id key
        workflows = self.cfgs.get("agent_workflows", {})
        if not isinstance(workflows, dict):
            logger.warning("Expected 'agent_workflows' to be a dictionary.")
            return []

        workflow = workflows.get(workflow_id)
        if not isinstance(workflow, dict):
            logger.warning(f"Workflow '{workflow_id}' not found or malformed.")
            return []

        sequence_str = workflow.get("agent_sequence", "")
        if not isinstance(sequence_str, str) or not sequence_str.strip():
            logger.warning(
                f"No valid 'agent_sequence' string found for workflow '{workflow_id}'."
            )
            return []

        # Parse the sequence using '>' separator and strip whitespace
        agent_ids = [
            agent.strip() for agent in sequence_str.split(">") if agent.strip()
        ]
        if not agent_ids:
            logger.warning(
                f"Agent sequence for workflow '{workflow_id}' is empty after parsing."
            )

        logger.info(f"Workflow '{workflow_id}' agent sequence: {agent_ids}")
        return agent_ids
