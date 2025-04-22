import json
import logging
import asyncio
from typing import Optional

from agno.agent import Agent, RunResponse
from agno.workflow import Workflow, RunEvent

from callbacks import log_agno_callbacks
from schemas import EpicList, StoryList, IssueList
from utils_agno import load_config, resolve_model
from agents.EpicAgent import build_epic_agent
from agents.StoryAgent import build_story_agent
from agents.IssueAgent import build_issue_agent
from agents.GraphAgent import build_graph_agent
from tools import (
    jira_search,
    jira_get_epic_issues,
    jira_get_issue_loop,
    arango_upsert,
)


# === Setup Logging ===
logging.basicConfig(
    level=logging.INFO,  # Set to DEBUG for more verbose Agno internal logs
    format="%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
logger = logging.getLogger(__name__)

# === Load Configuration ===
runtime_params = load_config("runtime")

# Models
provider = "openai"
models = runtime_params["MODELS"][provider]
MODEL_EPIC = resolve_model(provider=provider, model_id=models["epic"])
MODEL_STORY = resolve_model(provider=provider, model_id=models["story"])
MODEL_ISSUE = resolve_model(provider=provider, model_id=models["issue"])
MODEL_GRAPH = resolve_model(provider=provider, model_id=models["graph"])

# Session params
session_params = runtime_params["SESSION"]
SESSION_ID = session_params.get("session_id", "org_chart_tests")

# State keys
STATE_KEY_EPICS = runtime_params["SESSION"]["state_epics"]
STATE_KEY_STORIES = runtime_params["SESSION"]["state_stories"]
STATE_KEY_ISSUES = runtime_params["SESSION"]["state_issues"]

# Tools lists
TOOLS_EPIC = [jira_search]
TOOLS_STORY = [jira_get_epic_issues]
TOOLS_ISSUE = [jira_get_issue_loop]
TOOLS_GRAPH = [arango_upsert]


# === Define the Workflow ===


class JiraGraphWorkflow(Workflow):
    """
    Orchestrates the sequential process of fetching Jira data (Epics, Stories, Issues) and updating an ArangoDB graph.
    """

    description: str = "Fetches Jira data and updates ArangoDB graph sequentially."

    # Epic Agent (doesn't need initial state for prompt)
    epic_agent: Agent = build_epic_agent(model=MODEL_EPIC, tools=TOOLS_EPIC)

    async def _run_agent_step(
        self,
        agent: Agent,
        step_name: str,
        trigger_message: str,
        expected_output_type: Optional[type] = None,
        output_state_key: Optional[str] = None,
    ) -> bool:
        """
        Helper function to run an agent step, handle errors, and store state.
        """
        logger.info(f"--- Workflow Step: {step_name} ---")
        agent.debug_mode = False
        try:
            # Use the workflow's session_id for the agent run
            response: RunResponse = await agent.arun(
                trigger_message, session_id=self.session_id
            )

            if not response or response.content is None:
                logger.error(f"{step_name} failed: No content from Agent.")
                self.session_state[f"{step_name}_error"] = "Agent returned no content"
                return False

            # Validate output type if expected
            if expected_output_type and not isinstance(
                response.content, expected_output_type
            ):
                logger.error(
                    f"{step_name} failed: Expected output type {expected_output_type}, got {type(response.content)}"
                )
                self.session_state[f"{step_name}_error"] = (
                    f"Invalid output type: {type(response.content)}"
                )
                self.session_state[f"{step_name}_raw_output"] = (
                    response.content
                )  # Store raw output for debugging
                return False
            logger.info(f"{step_name} completed successfully.")

            # Store successful output in session_state if key provided
            if output_state_key:
                self.session_state[output_state_key] = response.content
                logger.info(f"Stored result in session_state key: '{output_state_key}'")

            return True

        except Exception as e:
            logger.exception(f"{step_name} failed with exception.")
            self.session_state[f"{step_name}_error"] = str(e)
            return False

    async def arun(
        self, trigger_message: str = "Start Jira to Graph process."
    ) -> RunResponse:
        """
        Executes the sequential Jira to Graph workflow.
        """
        logger.info(f"Starting JiraGraphWorkflow with session_id: {self.session_id}")

        # === Step 1: Fetch Epics ===
        step1_success = await self._run_agent_step(
            agent=self.epic_agent,
            step_name="FetchEpics",
            trigger_message=trigger_message,
            expected_output_type=EpicList,
            output_state_key=STATE_KEY_EPICS,
        )
        if not step1_success:
            return RunResponse(
                content=f"Workflow failed at FetchEpics: {self.session_state.get('FetchEpics_error', 'Unknown error')}",
                event=RunEvent.workflow_failed,
                run_id=self.run_id,
            )

        # === Step 2: Graph Epics ===
        epics_data = self.session_state.get(STATE_KEY_EPICS)
        if not epics_data or not epics_data.epics:
            logger.warning(
                "No epics found or loaded to graph. Skipping GraphEpics and subsequent steps."
            )
        else:
            graph_epic_agent = build_graph_agent(
                model=MODEL_GRAPH,
                tools=TOOLS_GRAPH,
                initial_state={STATE_KEY_EPICS: json.dumps(epics_data.model_dump())},
                prompt_key="epic_graph_prompt",
            )
            step2_success = await self._run_agent_step(
                agent=graph_epic_agent,
                step_name="GraphEpics",
                trigger_message="Update graph based on initial epic data.",
            )
            if not step2_success:
                return RunResponse(
                    content=f"Workflow failed at GraphEpics: {self.session_state.get('GraphEpics_error', 'Unknown error')}",
                    event=RunEvent.workflow_failed,
                    run_id=self.run_id,
                )

        # === Step 3: Fetch Stories ===
        if not epics_data or not epics_data.epics:
            logger.warning(
                "No epics data available. Skipping FetchStories and subsequent steps."
            )
        else:
            story_agent = build_story_agent(
                model=MODEL_STORY,
                tools=TOOLS_STORY,
                initial_state={STATE_KEY_EPICS: json.dumps(epics_data.model_dump())},
            )
            step3_success = await self._run_agent_step(
                agent=story_agent,
                step_name="FetchStories",
                trigger_message="Fetch stories based on initial epic data.",
                expected_output_type=StoryList,
                output_state_key=STATE_KEY_STORIES,
            )
            if not step3_success:
                return RunResponse(
                    content=f"Workflow failed at FetchStories: {self.session_state.get('FetchStories_error', 'Unknown error')}",
                    event=RunEvent.workflow_failed,
                    run_id=self.run_id,
                )

        # === Step 4: Graph Stories ===
        stories_data = self.session_state.get(STATE_KEY_STORIES)
        if not stories_data or not stories_data.stories:
            logger.warning(
                "No stories found or loaded to graph. Skipping GraphStories and subsequent steps."
            )
        else:
            graph_story_agent = build_graph_agent(
                model=MODEL_GRAPH,
                tools=TOOLS_GRAPH,
                initial_state={
                    STATE_KEY_STORIES: json.dumps(stories_data.model_dump())
                },
                prompt_key="story_graph_prompt",
            )
            step4_success = await self._run_agent_step(
                agent=graph_story_agent,
                step_name="GraphStories",
                trigger_message="Update graph based on initial story data.",
            )
            if not step4_success:
                return RunResponse(
                    content=f"Workflow failed at GraphStories: {self.session_state.get('GraphStories_error', 'Unknown error')}",
                    event=RunEvent.workflow_failed,
                    run_id=self.run_id,
                )

        # === Step 5: Fetch Issues ===
        if not stories_data or not stories_data.stories:
            logger.warning(
                "No stories data available. Skipping FetchIssues and subsequent steps."
            )
        else:
            issue_agent = build_issue_agent(
                model=MODEL_ISSUE,
                tools=TOOLS_ISSUE,
                initial_state={
                    STATE_KEY_STORIES: json.dumps(stories_data.model_dump())
                },
            )
            step5_success = await self._run_agent_step(
                agent=issue_agent,
                step_name="FetchIssues",
                trigger_message="Fetch issue details based on initial story data.",
                expected_output_type=IssueList,
                output_state_key=STATE_KEY_ISSUES,
            )
            if not step5_success:
                return RunResponse(
                    content=f"Workflow failed at FetchIssues: {self.session_state.get('FetchIssues_error', 'Unknown error')}",
                    event=RunEvent.workflow_failed,
                    run_id=self.run_id,
                )

        # === Step 6: Graph Issues ===
        issues_data = self.session_state.get(STATE_KEY_ISSUES)
        if not issues_data or not issues_data.issues:
            logger.warning("No issues found or loaded to graph. Skipping GraphIssues.")
        else:
            graph_issue_agent = build_graph_agent(
                model=MODEL_GRAPH,
                tools=TOOLS_GRAPH,
                initial_state={STATE_KEY_ISSUES: json.dumps(issues_data.model_dump())},
                prompt_key="issue_graph_prompt",
            )
            step6_success = await self._run_agent_step(
                agent=graph_issue_agent,
                step_name="GraphIssues",
                trigger_message="Update graph based on initial issue data.",
            )
            if not step6_success:
                return RunResponse(
                    content=f"Workflow failed at GraphIssues: {self.session_state.get('GraphIssues_error', 'Unknown error')}",
                    event=RunEvent.workflow_failed,
                    run_id=self.run_id,
                )

        # === Workflow Complete ===
        logger.info(
            f"JiraGraphWorkflow completed successfully for session_id: {self.session_id}"
        )
        final_message = "Workflow completed successfully."

        return RunResponse(
            content=final_message,
            event=RunEvent.workflow_completed,
            run_id=self.run_id,  # Use workflow run_id
        )


# === Main Execution Block ===


async def main():
    """
    Runs the sequential workflow.
    """
    logger.info(f"Initializing workflow with session ID: {SESSION_ID}")

    # Create or load the workflow session
    workflow = JiraGraphWorkflow(
        session_id=SESSION_ID,
    )

    logger.info("Running workflow...")
    final_response = await workflow.arun()
    run_label = "SequentialRun"
    log_agno_callbacks(final_response, run_label, filename=f"{run_label}_callbacks")
    logger.info("Workflow finished.")

    logger.info(f"Final Workflow Status: {final_response.event}")
    logger.info(f"Final Workflow Message: {final_response.content}")

    # Optional: Inspect final workflow state
    logger.debug("--- Final Workflow Session State ---")
    logger.debug(workflow.session_state)
    logger.debug("--- End Final Workflow State ---")


if __name__ == "__main__":
    asyncio.run(main())
