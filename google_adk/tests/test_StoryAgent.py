import asyncio
import json
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner

from debug_callbacks import debug_before_tool, debug_before_model
from google_adk.tools import jira_mcp_tools
from google_adk.agents.StoryAgent import get_story_agent

APP_NAME = "jira_test_app"
USER_ID = "test_user"
SESSION_ID = "story_test_session"
EPIC_FILE = "google_adk/tests/epic_test_data.json"
QUERY = "Get all stories from the given epics."


async def test_story_agent():
    # Setup in-memory services
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()

    # Reset session
    session_service.delete_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )
    session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    # Load epic test data
    with open(EPIC_FILE, "r") as f:
        epic_data = json.load(f)

    # Set epic data in session state (as if returned from EpicAgent)
    session = session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    session.state["epics_raw"] = json.dumps(epic_data)

    # Load tools and agent
    tools, exit_stack = await jira_mcp_tools()
    story_agent = get_story_agent(
        tools, tool_debug=debug_before_tool, model_debug=debug_before_model
    )

    runner = Runner(
        agent=story_agent,
        app_name=APP_NAME,
        session_service=session_service,
        artifact_service=artifact_service,
    )

    content = types.Content(role="user", parts=[types.Part(text=QUERY)])

    async with exit_stack:
        async for event in runner.run_async(
            user_id=USER_ID, session_id=SESSION_ID, new_message=content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                print("\n--- Final LLM Output ---")
                print(event.content.parts[0].text)

    print("MCP server cleanup...")
    await exit_stack.aclose()


if __name__ == "__main__":
    asyncio.run(test_story_agent())
