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
    Orchestrates the agent-based execution of the research pipeline.

    Behavior:
        - Initializes shared state, agent instances, config, and DB.
        - Dispatches events to agents and monitors progress.
        - Terminates when the pipeline completes (EXTRACTION_COMPLETE) or fails.
    """

    def __init__(
        self,
        company: str,
        workflow_id: str,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ):
        self.company = company
        self.workflow_id = workflow_id
        self.progress_callback = progress_callback
        self.arangodb_manager: Optional[ArangoDBManager] = None

        # Dictionary to route events to agents
        self.agent_map: Dict[EventType, BaseAgent] = {}

        self._load_config()
        self._init_arangodb()
        self._prepare_state()
        self._init_agents()
        self._init_event_queue()
        self._log("Initialization complete.")

    def _log(
        self,
        message: str = None,
        type_: str = "agent_log",
        agent_name="Orchestrator",
        event_type: Optional[str] = None,
    ):
        if self.progress_callback:
            try:
                update = {
                    "type": type_,
                    "agent_name": agent_name,
                    "message": message,
                    "event_type": event_type,
                }
                self.progress_callback(update)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}", exc_info=False)

    def _load_config(self):
        try:
            self.secrets = Secrets()
            self.loader = ConfigLoader()
            self.cfg = self.loader.get_all_configs()
            self._log("Config loaded.")
        except Exception as e:
            raise RuntimeError(f"Failed to load configuration: {e}") from e

    def _init_arangodb(self):
        """
        Initializes the ArangoDB manager and ensures collections.
        """
        try:
            self.arangodb_manager = ArangoDBManager(
                host=self.secrets.ARANGO_HOST,
                db_name=self.secrets.ARANGO_DB,
                usr=self.secrets.ARANGO_USR,
                pwd=self.secrets.ARANGO_PWD,
            )

            # Ensure collections exist using entities & relationships in config
            self.arangodb_manager.ensure_collections(
                list(self.cfg.get("entity_types", {}).values()),
                list(self.cfg.get("relationship_types", {}).values()),
            )
            self._log("ArangoDB collections ensured.", type_="agent_log")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize ArangoDB: {e}") from e

    def _prepare_state(self):
        """
        Selects and prepares the output schema.
        """
        try:
            # Fetch the schema by ID from the loaded config
            schema_id = self.cfg.get("runtime_settings", {}).get("schema_id_to_use")
            schema_entry = self.cfg.get("output_schemas", {}).get(schema_id)

            if not schema_entry or not isinstance(schema_entry.get("schema"), dict):
                raise ValueError(f"Invalid or missing schema for ID: {schema_id}")

            # Initialize state with chosen schemanfor use across agents
            self.state = OverallState(
                company=self.company, output_schema=schema_entry["schema"]
            )
            self._log(f"Using schema: {schema_id}")
        except Exception as e:
            raise RuntimeError(f"Schema preparation failed: {e}") from e

    def _init_agents(self):
        """
        Instantiates all agents defined in the workflow.
        Note: workflow is not properly implemented yet!
        """
        self.agents = create_agents(
            state=self.state,
            config=self.cfg,
            arangodb_manager=self.arangodb_manager,
        )
        self._log(f"Created {len(self.agents)} agents.")

        # Build the routing map between EventType and the corresponding agent
        self.agent_map = self._map_events_to_agents(self.agents)
        agent_names = [a.name for a in self.agents]
        self._log(f"Created agents: {', '.join(agent_names)}")

    def _init_event_queue(self):
        """
        Initializes a shared queue for agents to push/pull events.
        """
        self.event_queue = asyncio.Queue()
        self._log("Event queue initialized.")

    def _map_events_to_agents(
        self, agents: list[BaseAgent]
    ) -> Dict[EventType, BaseAgent]:
        """
        Routing between events and agents (hardcoded for now!).
        The orchestrator will act as the central coordinator and dispatch events to the appropiate agent.
        """
        mapping = {}
        for agent in agents:
            if agent.name == "GraphQueryAgent":
                mapping[EventType.START_RESEARCH] = agent

            elif agent.name == "QueryGenerationAgent":
                mapping[EventType.NEED_EXTERNAL_DATA] = agent

            elif agent.name == "WebSearchAgent":
                mapping[EventType.QUERIES_GENERATED] = agent

            elif agent.name == "ResearchAgent":
                mapping[EventType.SEARCH_RESULTS_READY] = agent

            elif agent.name == "ExtractionAgent":
                mapping[EventType.RESEARCH_COMPILED] = agent

            elif agent.name == "GraphUpdateAgent":
                mapping[EventType.EXTRACTION_COMPLETE] = agent

        return mapping

    async def start(self) -> Dict[str, Any]:
        """
        Begins the full agentic pipeline by pushing the START_RESEARCH event.
        """
        await self.event_queue.put(Event(EventType.START_RESEARCH))

        # Define the events to terminate the pipeline
        terminal_events = {
            EventType.GRAPH_UPDATE_COMPLETE,
            EventType.GRAPH_DATA_FOUND,
            EventType.ERROR_OCCURRED,
        }

        # Continue dispatching events to agents until terminal event is reached
        while True:
            event = await self.event_queue.get()

            # This is not a true log since type_="event"
            self._log(
                "Orchestrator received event:",
                type_="event",
                event_type=event.type.name,
            )

            if event.type in terminal_events:
                return await self._handle_termination(event)

            await self._dispatch_event(event)

    async def _dispatch_event(self, event: Event):
        """
        Routes an event to its mapped agent who begins handling the event.
        """
        agent = self.agent_map.get(event.type)
        if not agent:
            self._log(f"No agent mapped for event: {event.type.name}", type_="warning")
            return

        self._log(type_="dispatch", agent_name=agent.name, event_type=event.type.name)
        try:
            await agent.handle_event(event, self.event_queue, self.progress_callback)
        except Exception as e:
            error_msg = f"Agent {agent.name} failed on {event.type.name}: {e}"
            self._log(error_msg, type_="error")
            await self.event_queue.put(
                Event(EventType.ERROR_OCCURRED, payload={"error": error_msg})
            )

    async def _handle_termination(self, event: Event) -> Dict[str, Any]:
        """
        Final step: formats the final result, logs the end status, and sends a pipeline_end message via progress_callback.
        """
        result = {}
        status = "error"
        message = "Pipeline terminated unexpectedly."

        if event.type == EventType.GRAPH_UPDATE_COMPLETE:
            status = "success"
            message = "Graph update completed."
            result = self.state.final_output

        elif event.type == EventType.GRAPH_DATA_FOUND:
            status = "success"
            message = "Graph data found — skipping enrichment."
            result = {
                "status": "Data found in graph",
                "results": self.state.graph_query_results,
            }
            self.state.complete = True

        elif event.type == EventType.ERROR_OCCURRED:
            error_text = event.payload.get("error", "Unknown error")
            message = f"Pipeline error: {error_text}"
            result = {"error": message}
            self.state.complete = False

        if self.progress_callback:
            try:
                self.progress_callback(
                    {
                        "type": "pipeline_end",
                        "status": status,
                        "message": message,
                        "result": result,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to send pipeline end status: {e}")


async def run_research_pipeline(
    company: str,
    workflow_id: str,
    progress_callback: Optional[Callable[[Dict], None]] = None,
) -> Dict[str, Any]:
    """
    xternal entry point to start the system. Creates the Orchestrator, starts it, and returns its output.
    """
    orchestrator = Orchestrator(company, workflow_id, progress_callback)
    return await orchestrator.start()
