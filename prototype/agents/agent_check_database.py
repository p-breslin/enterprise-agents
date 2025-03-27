from ..base_agent import BaseAgent
from ..events import Event, EventType
from app.main.embedding_search import EmbeddingSearch


class DatabaseAgent(BaseAgent):
    """
    1.  Listens for START_RESEARCH. When triggered:
    2.  Checks whether relevant data is already stored in a database.
    3.  If data; stores it in state.search_results and notifies other agents.
        If no data; triggers query generation.
    """

    async def handle_event(self, event: Event, event_queue) -> None:
        """
        Overrides handle_event from BaseAgent.
        """
        if event.type == EventType.START_RESEARCH:
            self.log(f"Received {event.type.name} event.")
            await self.check_database(event_queue)

    async def check_database(self, event_queue) -> None:
        self.log("Checking the database...")

        vector_search = EmbeddingSearch(self.state.company)
        metadata, docs = vector_search.run()

        if not metadata:
            self.log("No stored data found; publishing NEED_QUERIES.")
            await event_queue.put(Event(EventType.NEED_QUERIES))
        else:
            self.log("Found data in DB; publishing DB_CHECK_DONE.")
            self.state.search_results = [
                {
                    "url": metadata["link"],
                    "title": metadata["title"],
                    "content": docs,
                    "raw_content": None,
                }
            ]
            await event_queue.put(Event(EventType.DB_CHECK_DONE))
