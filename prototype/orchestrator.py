import logging
import asyncio
from typing import Dict

from .events import Event, EventType
from .state import OverallState
from .factory import create_agents
from .base_agent import BaseAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")


class Orchestrator:
    """
    Orchestrates everything:
    1.  Creates events, shared OverallState, agents, and starts them all.
    2.  Publishes a START_RESEARCH event.
    3.  Waits for EXTRACTION_COMPLETE.
    """

    def __init__(self, company: str):
        self.company = company
        self.state = OverallState(company=company)
        self.event_queue = asyncio.Queue()

        # Agent will not access the event queue; only the orchestrator
        self.agents = create_agents(state=self.state)

        # Dictionary to map each EventType to each agent
        self.agent_map: Dict[EventType, BaseAgent] = {}

        # route_event() will determine what event goes to what agent
        self.route_event()

    def route_event(self):
        """
        Event routing: the orchestrator will act as the central coordinator and dispatch events to the appropiate agent.
        """
        for agent in self.agents:
            if agent.name == "DatabaseAgent":
                self.agent_map[EventType.START_RESEARCH] = agent

            if agent.name == "QueryGenerationAgent":
                self.agent_map[EventType.NEED_QUERIES] = agent

            if agent.name == "WebSearchAgent":
                self.agent_map[EventType.QUERIES_GENERATED] = agent

            if agent.name == "ResearchAgent":
                self.agent_map[EventType.DB_CHECK_DONE] = agent
                self.agent_map[EventType.SEARCH_RESULTS_READY] = agent

            if agent.name == "ExtractionAgent":
                self.agent_map[EventType.RESEARCH_COMPILED] = agent

    async def start_system(self):
        """
        Starts all agents and coordinates the system until EXTRACTION_COMPLETE event is receieved.
        """
        logging.info("Agentic System Initiating...")

        # Initiate the pipeline
        await self.event_queue.put(Event(EventType.START_RESEARCH))

        # The orchestrator will ontinuously consume events from the queue
        while True:
            event = await self.event_queue.get()
            logging.info(f"[Orchestrator] Received event: {event.type.name}")

            # Shutdown process when extraction is complete
            if event.type == EventType.EXTRACTION_COMPLETE:
                logging.info("Extraction complete. Shutting down.")
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
            logging.warning(f"No agent mapped to handle event type {event.type.name}.")


async def run_research_pipeline(company: str):
    """
    A helper function that sets up the Orchestrator, runs the system, and returns final state.
    """
    orchestrator = Orchestrator(company=company)
    final_output = await orchestrator.start_system()
    return final_output


if __name__ == "__main__":
    # local testing
    company_to_research = "Nvidia"
    result = asyncio.run(run_research_pipeline(company_to_research))
    print("\n===Final results===")
    for field in result:
        print(f"{field}: {result[field]}")
