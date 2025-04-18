from google.adk.runners import Runner
from google.adk.agents import SequentialAgent
from google.adk.sessions import InMemorySessionService

from google_adk.tests.debug_callbacks import save_trace_event
from google_adk.utils_adk import load_config, load_tools, resolve_model

from google_adk.agents.EpicAgent import build_epic_agent
from google_adk.agents.StoryAgent import build_story_agent
from google_adk.agents.IssueAgent import build_issue_agent
from google_adk.agents.GraphUpdateAgent import build_graph_agent

# Change this
model_provider = "openai"

# Runtime parameters from configuration file
RUNTIME_PARAMS = load_config("runtime")

app_name = RUNTIME_PARAMS["SESSION"]["app_name"]
user_id = RUNTIME_PARAMS["SESSION"]["user_id"]
session_id = RUNTIME_PARAMS["SESSION"]["session_id"]

MODELS = RUNTIME_PARAMS["MODELS"][model_provider]
MODEL_EPIC = resolve_model(MODELS["epic"], provider=model_provider)
MODEL_STORY = resolve_model(MODELS["story"], provider=model_provider)
MODEL_ISSUE = resolve_model(MODELS["issue"], provider=model_provider)
MODEL_GRAPH = resolve_model(MODELS["graph"], provider=model_provider)

NAMES = RUNTIME_PARAMS["AGENT_NAMES"]
STAGE2 = NAMES["stage2"]
STAGE3 = NAMES["stage3"]
STAGE4 = NAMES["stage4"]


async def main():
    # Load tools (MCP tool servers)
    jira_mcp, exit_stack, jira_custom, arango_custom = await load_tools()

    # Initialize session
    session_service = InMemorySessionService()
    session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    # Compose pipeline
    pipeline_agent = SequentialAgent(
        name="JiraGraphPipeline",
        sub_agents=[
            build_epic_agent(
                model=MODEL_EPIC,
                tools=jira_mcp,
                output_key="outputs_EpicAgent",
            ),
            build_graph_agent(
                model=MODEL_GRAPH,
                tools=[arango_custom],
                input_key="outputs_EpicAgent",
                output_key="outputs_GraphAgent",
            ),
            build_story_agent(
                model=MODEL_STORY,
                tools=[jira_custom],
                input_key="outputs_EpicAgent",
                output_key="outputs_StoryAgent",
            ),
            build_graph_agent(
                model=MODEL_GRAPH,
                tools=[arango_custom],
                input_key="outputs_StoryAgent",
                output_key="outputs_GraphAgent",
            ),
            build_issue_agent(
                model=MODEL_ISSUE,
                tools=jira_mcp,
                input_key="outputs_StoryAgent",
                output_key="outputs_IssueAgent",
            ),
            build_graph_agent(
                model=MODEL_GRAPH,
                tools=[arango_custom],
                input_key="outputs_IssueAgent",
                output_key="outputs_GraphAgent",
            ),
        ],
    )

    # Attach runner
    runner = Runner(
        agent=pipeline_agent,
        app_name=app_name,
        session_service=session_service,
    )

    user_prompt = "Follow instructions."
    async with exit_stack:
        print("Running Sequential Pipeline...")
        async for event in runner.run(
            user_id=user_id, session_id=session_id, new_message=user_prompt
        ):
            save_trace_event(event, name="test")
            if event.is_final_response():
                print(f"\nFinal Response:\n{event.content.parts[0].text}")
