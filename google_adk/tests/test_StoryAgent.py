import asyncio
import json
from dotenv import load_dotenv
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner

from debug_callbacks import trace_event
from google.adk.tools.function_tool import FunctionTool
from google_adk.tools.custom_tools import jira_get_epic_issues
from google_adk.agents.StoryAgent import get_story_agent

load_dotenv()

APP_NAME = "jira_test_app"
USER_ID = "test_user"
SESSION_ID = "story_test_session"

with open("google_adk/tests/test_data/epic_test_data.json", "r") as f:
    epic_data = json.load(f)
epics_text = json.dumps(epic_data["epics"], indent=2)

QUERY = f"""
You must call the jira_get_epic_issues tool for each of the following epics:
{epics_text}
"""


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

    # Load tools and agent
    my_tool = FunctionTool(jira_get_epic_issues)
    story_agent = get_story_agent(tools=[my_tool])

    runner = Runner(
        agent=story_agent,
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
            print("\n--- Final LLM Output ---")
            print(event.content.parts[0].text)


if __name__ == "__main__":
    asyncio.run(test_story_agent())
