import logging
from scripts.config_loader import ConfigLoader

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s - %(message)s",
)


def test_config_loading():
    """
    Purpose:
        Loads all configurations and logs structure of key config types.
    """
    loader = ConfigLoader(cfg_dir="configs")

    # Individual config tests
    agent_config = loader.get_config("agent_config")
    prompt_templates = loader.get_config("prompt_templates")
    workflows = loader.get_config("agent_workflows")
    settings = loader.get_config("runtime_settings")

    if agent_config:
        logger.info("Sample Agent Config (Processed):")
        first_id = next(iter(agent_config), None)
        if first_id:
            logger.info(f"{first_id}: {agent_config[first_id]}")
        else:
            logger.warning("Agent config is empty.")

    if prompt_templates:
        logger.info(f"Loaded {len(prompt_templates)} prompt templates.")

    if workflows:
        logger.info(f"Loaded {len(workflows)} workflows.")
        logger.info(f"INITIAL_ANALYSIS: {workflows.get('INITIAL_ANALYSIS')}")

    if settings:
        logger.info("Runtime Settings:")
        logger.info(f"Tavily Params: {settings.get('tavily_search_params')}")
        logger.info(f"N_searches: {settings.get('N_searches')}")


def test_workflow_sequences():
    """
    Purpose:
        Tests workflow sequence parsing using valid and invalid workflow IDs.
    """
    loader = ConfigLoader(cfg_dir="configs")

    valid_id = "INITIAL_ANALYSIS"
    invalid_id = "NON_EXISTENT_WORKFLOW"

    sequence_valid = loader.load_workflow_sequence(valid_id)
    sequence_invalid = loader.load_workflow_sequence(invalid_id)

    logger.info(f"Workflow '{valid_id}' sequence: {sequence_valid}")
    logger.info(f"Workflow '{invalid_id}' sequence: {sequence_invalid}")


if __name__ == "__main__":
    logger.info("=== Running ConfigLoader Tests ===")
    try:
        test_config_loading()
        test_workflow_sequences()
    except Exception as e:
        logger.error(f"Test run failed: {e}", exc_info=True)
