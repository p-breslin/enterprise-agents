import json
import asyncio
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner

from debug_callbacks import trace_event
from google_adk.tools.ArangoUpsertTool import arango_upsert
from google.adk.tools.function_tool import FunctionTool
from google_adk.agents.GraphUpdateAgent import build_graph_agent


APP_NAME = "jira_test_app"
USER_ID = "test_user"
SESSION_ID = "graph_test_session"


def create_test(TEST_DATA):
    with open(
        f"google_adk/tests/test_data/simple/{TEST_DATA}_test_data.json", "r"
    ) as f:
        data = json.load(f)
    text = json.dumps(data, indent=2)
    QUERY = f"""
    Follow the instructions to execute the graph operation for the following data:
    {text}
    """
    PROMPT = f"{TEST_DATA}_graph_prompt"
    return QUERY, PROMPT


A = "epic"
B = "story"
C = "issue"
QUERY, PROMPT = create_test(C)


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

    # Create the GraphUpdateAgent and retrieve tools
    my_tools = FunctionTool(arango_upsert)
    graph_agent = build_graph_agent(tools=[my_tools], prompt=PROMPT)

    runner = Runner(
        agent=graph_agent,
        app_name=APP_NAME,
        session_service=session_service,
        artifact_service=artifact_service,
    )

    content = types.Content(role="user", parts=[types.Part(text=QUERY)])

    async for event in runner.run_async(
        user_id=USER_ID, session_id=SESSION_ID, new_message=content
    ):
        trace_event(event)
        if event.is_final_response() and event.content and event.content.parts:
            final_output = event.content.parts[0].text
            print("\n--- Final LLM Output ---")
            print(final_output)


if __name__ == "__main__":
    asyncio.run(test_graph_agent())
