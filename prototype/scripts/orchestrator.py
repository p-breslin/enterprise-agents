import logging
import asyncio
from typing import Dict, Any

from .state import OverallState
from .factory import create_agents
from .events import Event, EventType
from .config_loader import ConfigLoader
from agents.base_agent import BaseAgent

# Module-specific logger
logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Orchestrates everything:
    1.  Creates events, shared OverallState, agents, and starts them all.
    2.  Publishes a START_RESEARCH event.
    3.  Waits for EXTRACTION_COMPLETE.
    """

    def __init__(self, company: str, workflow_id: str):
        self.company = company
        self.workflow_id = workflow_id
        try:
            self.loader = ConfigLoader()
            self.cfg: Dict[str, Any] = self.loader.get_all_configs()
        except FileNotFoundError:
            logger.critical(
                "Config directory not found. Orchestrator cannot initialize.",
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.critical(f"Failed to load configurations: {e}", exc_info=True)
            raise

        # Select and prepare output schema
        try:
            schema_id_to_use = "COMPANY_INFO_BASIC"  # should put in a config
            logger.info(f"Using output schema ID: {schema_id_to_use}")

            # Fetch the schema entry from the loaded config
            schema_entry = self.cfg.get("output_schemas", {}).get(schema_id_to_use)
            if not schema_entry:
                raise ValueError(
                    f"Output schema with ID '{schema_id_to_use}' not found in configuration."
                )

            # Extract the actual schema definition part
            schema = schema_entry.get("schema")
            if not schema or not isinstance(schema, dict):
                raise ValueError(
                    f"Schema definition missing or invalid for schema ID '{schema_id_to_use}'."
                )

        except Exception as e:
            logger.critical(f"Failed to prepare output schema: {e}", exc_info=True)
            raise ValueError(f"Schema preparation failed: {e}") from e

        # Initialize state
        self.state = OverallState(company=company, output_schema=schema)

        # Load the workflow sequence
        self.agent_sequence_ids: list[str] = self.loader.load_workflow_sequence(
            self.workflow_id, self.cfg
        )

        # Just logging for now but aim for this to drive agent creation/routing
        logger.info(
            f"Target agent sequence for workflow '{self.workflow_id}': {self.agent_sequence_ids}"
        )
        if not self.agent_sequence_ids:
            # Decide how to handle missing/empty sequence - warning or error?
            logger.warning(
                f"Workflow '{self.workflow_id}' has an empty or invalid agent sequence."
            )
            # raise ValueError(f"Workflow '{self.workflow_id}' defines no agents.")

        # Setup the event queue
        self.event_queue = asyncio.Queue()

        # Agent will not access the event queue; only the orchestrator
        self.agents = create_agents(state=self.state, config=self.cfg)

        # Dictionary to map each EventType to each agent
        self.agent_map: Dict[EventType, BaseAgent] = {}

        # route_event() will determine what event goes to what agent
        self.route_event()

    def route_event(self):
        """
        Event routing: the orchestrator will act as the central coordinator and dispatch events to the appropiate agent.
        """
        logger.debug("Setting up static event routing map...")
        for agent in self.agents:
            if agent.name == "DatabaseAgent":
                self.agent_map[EventType.START_RESEARCH] = agent

            elif agent.name == "QueryGenerationAgent":
                self.agent_map[EventType.NEED_QUERIES] = agent

            elif agent.name == "WebSearchAgent":
                self.agent_map[EventType.QUERIES_GENERATED] = agent

            elif agent.name == "ResearchAgent":
                self.agent_map[EventType.DB_CHECK_DONE] = agent
                self.agent_map[EventType.SEARCH_RESULTS_READY] = agent

            elif agent.name == "ExtractionAgent":
                self.agent_map[EventType.RESEARCH_COMPILED] = agent

            else:
                logger.warning(f"Agent '{agent.name}' not included in static routing.")
        logger.debug(
            f"Agent map populated: { {k.name: v.name for k, v in self.agent_map.items()} }"
        )

    async def start_system(self):
        """
        Starts all agents and coordinates the system until EXTRACTION_COMPLETE event is receieved.
        """
        logger.info("Agentic System Initiating...")

        # Initiate the pipeline
        await self.event_queue.put(Event(EventType.START_RESEARCH))

        # The orchestrator will ontinuously consume events from the queue
        while True:
            event = await self.event_queue.get()
            logger.info(f"[Orchestrator] Received event: {event.type.name}")

            # Shutdown process when extraction is complete
            if event.type == EventType.EXTRACTION_COMPLETE:
                logger.info("Extraction complete. Shutting down.")
                break

            # Dispatch event to whichever agent handles it
            await self.dispatch_event(event)

        return self.state.final_output

    async def dispatch_event(self, event: Event):
        """
        Dispatches the event to the relevant agent.
        """
        if event.type in self.agent_map:
            agent = self.agent_map[event.type]
            await agent.handle_event(event, self.event_queue)
        else:
            logger.warning(f"No agent mapped to handle event type {event.type.name}.")


async def run_research_pipeline(company: str, workflow_id: str) -> Dict[str, Any]:
    """
    A helper function that sets up the Orchestrator for a given company and workflow. Runs the system, and returns final state.
    """
    final_output: Dict[str, Any] = {}
    try:
        orchestrator = Orchestrator(company=company, workflow_id=workflow_id)
        final_output = await orchestrator.start_system()
    except Exception as e:
        logger.error(f"Orchestrator failed to initialize or run: {e}", exc_info=True)
        final_output = {"error": f"Pipeline execution failed: {e}"}

    return final_output


if __name__ == "__main__":
    # local testing
    company_to_research = "Nvidia"
    default_workflow = "INITIAL_ANALYSIS"
    print(
        f"--- Running local test for '{company_to_research}' with workflow '{default_workflow}' ---"
    )

    result = asyncio.run(run_research_pipeline(company_to_research))
    print("\n===Final results===")
    for field in result:
        print(f"{field}: {result[field]}")
    print("--- Local test complete ---")
