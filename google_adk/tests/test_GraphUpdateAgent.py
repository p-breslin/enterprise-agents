import json
import asyncio
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner

from debug_callbacks import trace_event
from google_adk.tools.mcps import arango_mcp_tools
from google_adk.agents.GraphUpdateAgent import build_graph_agent


async def get_mcp_tools():
    tools, exit_stack = await arango_mcp_tools()
    return tools, exit_stack


APP_NAME = "jira_test_app"
USER_ID = "test_user"
SESSION_ID = "graph_test_session"

with open("google_adk/tests/test_data/epic_test_data_simple.json", "r") as f:
    epic_data = json.load(f)
epics_text = json.dumps(epic_data["epics"], indent=2)

QUERY = f"""
Follow the instructions to execute the graph operation for the following data:
{epics_text}
"""


async def test_graph_agent():
    # Create session and artifact services
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()

    # Debug
    session_service.delete_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )

    session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    # Create the GraphUpdateAgent and retrieve tools + exit stack
    tools, exit_stack = await get_mcp_tools()
    graph_agent = build_graph_agent(tools)

    runner = Runner(
        agent=graph_agent,
        app_name=APP_NAME,
        session_service=session_service,
        artifact_service=artifact_service,
    )

    content = types.Content(role="user", parts=[types.Part(text=QUERY)])

    async with exit_stack:
        async for event in runner.run_async(
            user_id=USER_ID, session_id=SESSION_ID, new_message=content
        ):
            trace_event(event)
            if event.is_final_response() and event.content and event.content.parts:
                final_output = event.content.parts[0].text
                print("\n--- Final LLM Output ---")
                print(final_output)

    # Ensure the MCP server process connection is closed
    print("Closing MCP server connection...")
    await exit_stack.aclose()


if __name__ == "__main__":
    asyncio.run(test_graph_agent())
