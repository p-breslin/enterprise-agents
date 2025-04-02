import logging
import asyncio
from typing import Dict, Any, Optional, Callable

from .state import OverallState
from .factory import create_agents
from .events import Event, EventType
from .config_loader import ConfigLoader
from agents.base_agent import BaseAgent
from .secrets import Secrets
from utilities.graph_db import ArangoDBManager

# Module-specific logger
logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Orchestrates everything:
    1.  Creates events, shared OverallState, agents, and starts them all.
    2.  Publishes a START_RESEARCH event.
    3.  Waits for EXTRACTION_COMPLETE.
    """

    def __init__(
        self,
        company: str,
        workflow_id: str,
        ui_callback: Optional[Callable[[Dict], None]] = None,
    ):
        self.company = company
        self.workflow_id = workflow_id
        self.ui_callback = ui_callback
        self.arangodb_manager: Optional[ArangoDBManager] = None

        try:
            self.secrets = Secrets()
            self.loader = ConfigLoader()
            self.cfg: Dict[str, Any] = self.loader.get_all_configs()
            self._send_ui_update(
                {
                    "type": "agent_log",
                    "agent_name": "Orchestrator",
                    "message": "Config loaded.",
                }
            )
        except FileNotFoundError:
            logger.critical(
                "Config directory not found. Orchestrator cannot initialize.",
                exc_info=True,
            )
            self._send_ui_update(
                {"type": "error", "message": "Config directory not found."}
            )
            raise
        except ValueError as e:
            logger.critical(f"Secrets configuration error: {e}", exc_info=True)
            self._send_ui_update({"type": "error", "message": f"Secrets Error: {e}"})
            raise
        except Exception as e:
            logger.critical(
                f"Failed to load configurations or secrets: {e}", exc_info=True
            )
            self._send_ui_update(
                {"type": "error", "message": f"Config/Secrets Load Error: {e}"}
            )
            raise

        # –– Initialize ArangoDB manager and ensure collections ––
        try:
            self.arangodb_manager = ArangoDBManager(
                host=self.secrets.ARANGO_HOST,
                db_name=self.secrets.ARANGO_DB,
                usr=self.secrets.ARANGO_USR,
                pwd=self.secrets.ARANGO_PWD,
            )
            # Fetch entity/relationship definitions from loaded config
            entity_types = list(self.cfg.get("entity_types", {}).values())
            relationship_types = list(self.cfg.get("relationship_types", {}).values())

            # Ensure collections exist based on config
            self.arangodb_manager.ensure_collections(entity_types, relationship_types)
            self._send_ui_update(
                {
                    "type": "agent_log",
                    "agent_name": "ArangoDBManager",
                    "message": "Collections ensured.",
                }
            )

        except ConnectionError as e:
            logger.critical(
                f"Failed to initialize ArangoDBManager: {e}. Graph features disabled.",
                exc_info=True,
            )
            self._send_ui_update(
                {"type": "error", "message": f"ArangoDB Connection Error: {e}"}
            )
            raise RuntimeError(f"ArangoDB connection failed: {e}") from e
        except Exception as e:
            logger.critical(
                f"Unexpected error during ArangoDB setup: {e}", exc_info=True
            )
            self._send_ui_update(
                {"type": "error", "message": f"ArangoDB Setup Error: {e}"}
            )
            raise RuntimeError(f"ArangoDB setup failed: {e}") from e

        # –– Select and prepare output schema ––
        try:
            runtime_settings = self.cfg.get("runtime_settings", {})
            schema_id_to_use = runtime_settings.get("schema_id_to_use")
            logger.info(f"Using output schema ID: {schema_id_to_use}")
            self._send_ui_update(
                {
                    "type": "agent_log",
                    "agent_name": "Orchestrator",
                    "message": f"Using schema: {schema_id_to_use}",
                }
            )

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
            self._send_ui_update(
                {"type": "error", "message": f"Schema Prep Error: {e}"}
            )
            raise ValueError(f"Schema preparation failed: {e}") from e

        # –– Initialize state ––
        self.state = OverallState(company=company, output_schema=schema)
        self._send_ui_update(
            {
                "type": "agent_log",
                "agent_name": "Orchestrator",
                "message": "OverallState initialized.",
            }
        )

        # –– Load the workflow sequence ––
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

        # –– Setup agents ––
        self.agents = create_agents(
            state=self.state, config=self.cfg, arangodb_manager=self.arangodb_manager
        )
        agent_names = [agent.name for agent in self.agents]
        self._send_ui_update(
            {
                "type": "agent_log",
                "agent_name": "Orchestrator",
                "message": f"Created agents: {', '.join(agent_names)}",
            }
        )

        # –– Setup the event queue and routing ––
        self.event_queue = asyncio.Queue()

        # Dictionary to map each EventType to each agent
        self.agent_map: Dict[EventType, BaseAgent] = {}

        # route_event() will determine what event goes to what agent
        self.route_event()  # Static routing needs update for new agents/events

        self._send_ui_update(
            {
                "type": "agent_log",
                "agent_name": "Orchestrator",
                "message": "Event queue and routing map ready.",
            }
        )

    def _send_ui_update(self, update: Dict[str, Any]):
        """
        Helper to safely call the UI callback if it exists.
        """
        if self.ui_callback:
            try:
                # Add timestamp or other common fields here?
                self.ui_callback(update)
            except Exception as e:
                logger.warning(f"UI callback failed: {e}", exc_info=False)

    def route_event(self):
        """
        Event routing: the orchestrator will act as the central coordinator and dispatch events to the appropiate agent.
        TO-DO: Make this dynamic based on selected workflow.
        """
        logger.debug("Setting up static event routing map...")
        self.agent_map = {}  # Clear any previous map
        for agent in self.agents:
            if agent.name == "GraphQueryAgent":
                self.agent_map[EventType.START_RESEARCH] = agent

            elif agent.name == "QueryGenerationAgent":
                self.agent_map[EventType.NEED_EXTERNAL_DATA] = agent

            elif agent.name == "WebSearchAgent":
                self.agent_map[EventType.QUERIES_GENERATED] = agent

            elif agent.name == "ResearchAgent":
                self.agent_map[EventType.SEARCH_RESULTS_READY] = agent

            elif agent.name == "ExtractionAgent":
                self.agent_map[EventType.RESEARCH_COMPILED] = agent

            # Route EXTRACTION_COMPLETE to GraphUpdateAgent
            elif agent.name == "GraphUpdateAgent":
                self.agent_map[EventType.EXTRACTION_COMPLETE] = agent

        # Log the final map
        mapped_events = list(self.agent_map.keys())
        logger.debug(
            f"Agent map populated. Handling events: {[e.name for e in mapped_events]}"
        )

    async def start_system(self):
        """
        Starts all agents and coordinates the system until EXTRACTION_COMPLETE event is receieved.
        Reports status via the UI callbacks.
        """

        # Initiate the pipeline
        logger.info("Agentic System Initiating...")
        await self.event_queue.put(Event(EventType.START_RESEARCH))

        final_event_types = {
            # Normal completion after enrichment
            EventType.GRAPH_UPDATE_COMPLETE,
            # Completion if graph had sufficient data initially
            EventType.GRAPH_DATA_FOUND,
            # Completion on error
            EventType.ERROR_OCCURRED,
        }

        final_output: Dict[str, Any] = {"status": "unknown"}

        # The orchestrator will ontinuously consume events from the queue
        while True:
            event = await self.event_queue.get()
            logger.info(f"[Orchestrator] Received event: {event.type.name}")

            # Report every event received
            self._send_ui_update(
                {
                    "type": "event",
                    "event_type": event.type.name,
                    "payload": event.payload,
                }
            )

            # –– Check for end conditions ––
            if event.type in final_event_types:
                status = "error"
                message = "An error occurred."

                if event.type == EventType.GRAPH_UPDATE_COMPLETE:
                    status = "success"
                    message = "Graph update complete. Pipeline finished successfully."
                    logger.info(message)
                    final_output = (
                        self.state.final_output
                        if self.state
                        else {"status": "completed"}
                    )

                elif event.type == EventType.GRAPH_DATA_FOUND:
                    status = "success"
                    message = (
                        "Graph data found. Pipeline finished (bypassed enrichment)."
                    )
                    logger.info(message)

                    # Prepare a specific output format for this case
                    final_output = {
                        "status": "Data found in graph",
                        "results": self.state.graph_query_results if self.state else [],
                    }
                    if self.state:
                        self.state.complete = True

                elif event.type == EventType.ERROR_OCCURRED:
                    status = "error"
                    error_payload = event.payload.get("error", "Unknown error")
                    message = f"Pipeline halting due to error: {error_payload}"
                    logger.error(message)
                    final_output = {"error": message}
                    if self.state:
                        self.state.complete = False

                # Send the final pipeline status update
                self._send_ui_update(
                    {
                        "type": "pipeline_end",
                        "status": status,
                        "message": message,
                        "result": final_output,  # Include final result for UI
                    }
                )
                break

            # Dispatch event to whichever agent handles it
            await self.dispatch_event(event)

        logger.info("Agentic System Shutdown.")
        return self.state.final_output

    async def dispatch_event(self, event: Event):
        """
        Dispatches the event to the relevant agent.
        """
        if event.type in self.agent_map:
            agent = self.agent_map[event.type]
            logger.debug(f"Dispatching {event.type.name} to {agent.name}")

            # Report the dispatch action
            self._send_ui_update(
                {
                    "type": "dispatch",
                    "event_type": event.type.name,
                    "agent_name": agent.name,
                }
            )
            try:
                # Pass event, queue, and callback to the agent
                await agent.handle_event(event, self.event_queue, self.ui_callback)

            # Handle errors from agent's handle_event if not caught inside
            except Exception as e:
                logger.error(
                    f"Error during handling of {event.type.name} by {agent.name}: {e}",
                    exc_info=True,
                )

                # Publish an error event to stop the pipeline
                error_payload = {
                    "error": f"Agent {agent.name} failed on event {event.type.name}: {e}"
                }
                await self.event_queue.put(
                    Event(EventType.ERROR_OCCURRED, payload=error_payload)
                )

                # Also send immediate UI update about this critical failure
                self._send_ui_update(
                    {"type": "error", "message": error_payload["error"]}
                )
        else:
            logger.warning(f"No agent mapped to handle event type {event.type.name}.")

            # Report the warning to UI
            self._send_ui_update(
                {
                    "type": "warning",
                    "message": f"No handler for event: {event.type.name}",
                }
            )


# --- Global Runner Function ---
async def run_research_pipeline(
    company: str, workflow_id: str, ui_callback: Optional[Callable[[Dict], None]] = None
) -> Dict[str, Any]:
    """
    A helper function that sets up the Orchestrator for a given company and workflow. Runs the system, and returns final state, all while passing the UI callback for status updates.
    """
    final_output: Dict[str, Any] = {}
    orchestrator: Optional[Orchestrator] = None

    try:
        # Pass the callback during initialization
        orchestrator = Orchestrator(
            company=company, workflow_id=workflow_id, ui_callback=ui_callback
        )
        final_output = await orchestrator.start_system()

    except Exception as e:
        logger.error(f"Orchestrator failed to initialize or run: {e}", exc_info=True)
        error_msg = f"Pipeline execution failed: {e}"
        final_output = {"error": error_msg}

        # If callback exists, send error
        if ui_callback:
            try:
                # Ensure a pipeline_end message is sent even on failure
                ui_callback(
                    {
                        "type": "pipeline_end",
                        "status": "error",
                        "message": error_msg,
                        "result": final_output,
                    }
                )
            except Exception as cb_e:
                logger.error(
                    f"Failed to send final error status via UI callback: {cb_e}"
                )

    return final_output


if __name__ == "__main__":
    # –– Local testing ––
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
