import asyncio
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.runners import Runner

from google_adk.pipeline import build_pipeline
from google_adk.tools.mcps import jira_mcp_tools
from debug_callbacks import trace_event


APP_NAME = "jira_graph_app"
USER_ID = "test_user"
SESSION_ID = "jira_graph_session"

QUERY = "Build the Jira knowledge graph."


async def main():
    # Load tools from Jira MCP
    jira_tools, exit_stack = await jira_mcp_tools()

    # Construct pipeline with tools injected
    pipeline = build_pipeline(jira_tools)

    # Setup session & artifact services
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()

    # Wipe and initialize session
    session_service.delete_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    runner = Runner(
        agent=pipeline,
        app_name=APP_NAME,
        session_service=session_service,
        artifact_service=artifact_service,
    )

    content = types.Content(role="user", parts=[types.Part(text=QUERY)])

    async with exit_stack:
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=content,
        ):
            trace_event(event)
            if event.is_final_response() and event.content:
                print("\nFinal Output:")
                print(event.content.parts[0].text)

    print("Pipeline complete.")


if __name__ == "__main__":
    asyncio.run(main())
