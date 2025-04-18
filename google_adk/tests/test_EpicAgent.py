import asyncio
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner

from debug_callbacks import trace_event
from google_adk.utils_adk import extract_json
from google_adk.tools.mcps import jira_mcp_tools
from google_adk.agents.EpicAgent import build_epic_agent


async def get_mcp_tools():
    tools, exit_stack = await jira_mcp_tools()
    return tools, exit_stack


APP_NAME = "jira_test_app"
USER_ID = "test_user"
SESSION_ID = "epic_test_session"
QUERY = "Get all epics updated in the last 30 days."


async def test_epic_agent():
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

    # Create the EpicAgent and retrieve tools + exit stack
    tools, exit_stack = await get_mcp_tools()
    epic_agent = build_epic_agent(model="gemini-2.0-flash", tools=tools)

    runner = Runner(
        agent=epic_agent,
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

    print(extract_json(raw_text=final_output, key="epics"))

    # Ensure the MCP server process connection is closed
    print("Closing MCP server connection...")
    await exit_stack.aclose()


if __name__ == "__main__":
    asyncio.run(test_epic_agent())
