import json
import asyncio
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner

from debug_callbacks import trace_event, save_trace_event
from google_adk.tools.ArangoUpsertTool import arango_upsert
from google.adk.tools.function_tool import FunctionTool
from google_adk.agents.GraphUpdateAgent import build_graph_agent


APP_NAME = "jira_test_app"
USER_ID = "test_user"


def create_test(TEST_DATA):
    with open(
        f"google_adk/tests/test_data/simple/{TEST_DATA}_test_data.json", "r"
    ) as f:
        data = json.load(f)
    text = json.dumps(data, indent=2)
    QUERY = f"Follow the instructions to execute the graph operation for the following data:\n{text}"
    PROMPT = f"{TEST_DATA}_graph_prompt"
    return QUERY, PROMPT


async def test_graph_agent(test_name):
    QUERY, PROMPT = create_test(test_name)
    SESSION_ID = f"{test_name}_test_session"

    # Setup session
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    session_service.delete_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )

    # Create GraphUpdateAgent
    tool = FunctionTool(arango_upsert)
    agent = build_graph_agent(tools=[tool], prompt=PROMPT)

    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
        artifact_service=artifact_service,
    )

    content = types.Content(role="user", parts=[types.Part(text=QUERY)])
    async for event in runner.run_async(
        user_id=USER_ID, session_id=SESSION_ID, new_message=content
    ):
        trace_event(event, debug_state=False)
        save_trace_event(event, test_name)
        if event.is_final_response():
            print(f"[{test_name}] Final event detected")


async def main():
    print("=== Running Epic Test ===")
    await test_graph_agent("epic")

    print("=== Running Story Test ===")
    await test_graph_agent("story")

    print("=== Running Issue Test ===")
    await asyncio.sleep(20)
    await test_graph_agent("issue")


if __name__ == "__main__":
    asyncio.run(main())
