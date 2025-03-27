import json
import asyncio
from typing import Any, List
from pydantic import BaseModel
from utils import is_valid_json
from dataclasses import dataclass
from prompts import PLAN_TASKS, RETRY_PLAN_TASKS
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.models import SystemMessage, UserMessage
from autogen_core import (
    RoutedAgent,
    AgentId,
    SingleThreadedAgentRuntime,
    MessageContext,
    message_handler,
)


# Structured output model for individual tasks
class Task(BaseModel):
    task: str
    description: str


# Structured output model for the planning result
class PlanStructure(BaseModel):
    tasks: List[Task]


@dataclass
class PlanQuery:
    """
    A message type that carries a query for planning.

    Attributes:
        query (str): The query string to analyze.
    """

    query: str


@dataclass
class PlanResponse:
    """
    A message type for carrying the planning results.

    Attributes:
        tasks (Any): A list of task dictionaries generated from the query.
    """

    tasks: Any


class PlannerAgent(RoutedAgent):
    """
    AutoGen agent designed to analyze queries and produce a plan in the form of a JSON-formatted list of tasks.

    Uses an OpenAI model (via OpenAIChatCompletionClient) to generate the plan.

    Handles messages of type PlanQuery and replies with a PlanResponse.
    """

    def __init__(self) -> None:
        """
        The agent type ("planner_agent") is used for routing and identity.
        """

        # Call the RoutedAgent constructor with the agent type
        super().__init__("planner_agent")

        # Initialize the model client with response instructions
        self.model_client = OpenAIChatCompletionClient(
            model="gpt-4o",
            response_format=PlanStructure,
        )

    @message_handler
    async def handle_plan_query(self, message: PlanQuery, ctx: MessageContext) -> None:
        """
        Handles incoming PlanQuery messages.

        Extracts the query from the message, constructs a prompt for the OpenAI model to generate a JSON list of tasks, and then processes the model's response.

        Args:
            message (PlanQuery): The message containing the enterprise query.
            ctx (MessageContext): Provides context for the message.

        """

        messages = [
            SystemMessage(content=PLAN_TASKS.format(query=message.query)),
            UserMessage(content=f"Company: {message.query}", source="user"),
        ]
        response = await self.model_client.create(messages=messages)
        json_check = is_valid_json(response.content)

        if json_check:
            return json.loads(response.content)

        # Retry logic
        attempt = 0
        json_check = False
        while not json_check and attempt < 3:
            messages = [
                SystemMessage(
                    content=RETRY_PLAN_TASKS.format(previous_response=response.content)
                ),
                UserMessage(content=f"Company: {message.query}", source="user"),
            ]
            response = await self.model_client.create(messages=messages)
            json_check = is_valid_json(response.content)
            if json_check:
                return json.loads(response.content)
            attempt += 1

        raise ValueError("Failed to generate valid JSON.")


async def main() -> None:
    """
    Main function to set up and test the PlannerAgent.

      1. Creates a SingleThreadedAgentRuntime for local development.
      2. Registers the PlannerAgent with the runtime.
      3. Starts the runtime's background message processing.
      4. Sends a sample PlanQuery message to the agent.
      5. Allows message processing, then stops and closes the runtime.
    """

    # Create a runtime instance for local, single-threaded execution
    runtime = SingleThreadedAgentRuntime()

    # Register the PlannerAgent with the runtime
    await PlannerAgent.register(runtime, "planner_agent", lambda: PlannerAgent())

    # Start the runtime's background processing of messages
    runtime.start()

    # Create an AgentId (the agent type and a key) for direct messaging
    agent_id = AgentId("planner_agent", "default")

    # Test message
    test_query = PlanQuery(query="Nvidia")

    # Send the PlanQuery message to the PlannerAgent
    await runtime.send_message(test_query, agent_id)

    # Allow some time for the agent to process the message
    await asyncio.sleep(2)

    # Stop processing and close the runtime
    await runtime.stop()
    await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
