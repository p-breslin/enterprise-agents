import asyncio
import json
import logging
from typing import Any, Coroutine, List

from agno.agent import Agent, RunResponse
from agno.workflow import RunEvent, Workflow

from callbacks import log_agno_callbacks
from utils_agno import load_config, resolve_model
from schemas import Epic, EpicList, Story, StoryList, Issue, IssueList

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

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CFG = load_config("runtime")
PROVIDER = "openai"
MODELS = CFG["MODELS"][PROVIDER]
PROMPTS = CFG["PROMPTS"]
SESSION_PARAMS = CFG["SESSION"]

MODEL_EPIC = resolve_model(PROVIDER, MODELS["epic"])
MODEL_STORY = resolve_model(PROVIDER, MODELS["story"])
MODEL_ISSUE = resolve_model(PROVIDER, MODELS["issue"])
MODEL_GRAPH = resolve_model(PROVIDER, MODELS["graph"])

MAX_CONCURRENCY = SESSION_PARAMS.get("max_concurrency", 15)
SESSION_ID = SESSION_PARAMS.get("session_id", "org_chart_tests")
SAVE_NAME = "test_workflow"

STATE_KEYS = {
    "EPICS": CFG["SESSION"]["state_epics"],
    "STORIES": CFG["SESSION"]["state_stories"],
    "ISSUES": CFG["SESSION"]["state_issues"],
}

TOOLS = {
    "EPIC": [jira_search],
    "STORY": [jira_get_epic_issues],
    "ISSUE": [jira_get_issue_loop],
    "GRAPH": [arango_upsert],
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
log = logging.getLogger(__name__)

DEBUG = True


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
async def run_with_semaphore(
    coro: Coroutine, sem: asyncio.Semaphore, label: str
) -> Any:
    """Wrapper that limits concurrency and converts exceptions to results."""
    async with sem:
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001 – we *want* the object
            log.error("Task %s failed: %s", label, exc, exc_info=True)
            return exc


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
class JiraGraphWorkflow(Workflow):
    """Fetch Jira data and update the ArangoDB graph with four async stages."""

    epic_agent: Agent = build_epic_agent(
        model=MODEL_EPIC, tools=TOOLS["EPIC"], prompt=PROMPTS["epic"], debug=DEBUG
    )

    # -------------------------------------------------------------------
    # Stage 1 – fetch epics
    # -------------------------------------------------------------------
    async def _get_epics(self, trigger: str) -> EpicList:
        resp = await self.epic_agent.arun(trigger, session_id=self.session_id)
        if not isinstance(resp.content, EpicList):
            raise TypeError("Stage 1 returned non-EpicList")

        # log_agno_callbacks(resp, "EpicAgent", SAVE_NAME, overwrite=False)
        self.session_state[STATE_KEYS["EPICS"]] = resp.content
        return resp.content

    # -------------------------------------------------------------------
    # Stage 2 – graph epics & fetch stories
    # -------------------------------------------------------------------
    async def _process_epic(self, epic: Epic) -> List[Story]:
        epic_state = {STATE_KEYS["EPICS"]: json.dumps(epic.model_dump())}

        graph_coro = build_graph_agent(
            model=MODEL_GRAPH,
            tools=TOOLS["GRAPH"],
            initial_state=epic_state,
            prompt=PROMPTS["graph_epic"],
            debug=DEBUG,
        ).arun(f"Update graph for epic {epic.epic_key}.", session_id=self.session_id)

        story_coro = build_story_agent(
            model=MODEL_STORY,
            tools=TOOLS["STORY"],
            initial_state=epic_state,
            prompt=PROMPTS["story"],
            debug=DEBUG,
        ).arun(f"Fetch stories for epic {epic.epic_key}.", session_id=self.session_id)

        graph_resp, story_resp = await asyncio.gather(graph_coro, story_coro)
        # log_agno_callbacks(
        #     graph_resp, f"EpicGraph_{epic.epic_key}", SAVE_NAME, overwrite=False
        # )
        # log_agno_callbacks(
        #     story_resp, f"StoryAgent_{epic.epic_key}", SAVE_NAME, overwrite=False
        # )

        if isinstance(story_resp.content, StoryList):
            return story_resp.content.stories
        raise TypeError("Story agent returned wrong type")

    # -------------------------------------------------------------------
    # Stage 3 – graph stories & fetch issues
    # -------------------------------------------------------------------
    async def _graph_story(self, story: Story) -> None:
        story_state = {STATE_KEYS["STORIES"]: json.dumps(story.model_dump())}
        agent = build_graph_agent(
            model=MODEL_GRAPH,
            tools=TOOLS["GRAPH"],
            initial_state=story_state,
            prompt=PROMPTS["graph_story"],
            debug=DEBUG,
        )
        graph_resp = await agent.arun(
            f"Update graph for story {story.story_key}.", session_id=self.session_id
        )
        # log_agno_callbacks(
        #     graph_resp, f"StoryGraph_{story.story_key}", SAVE_NAME, overwrite=False
        # )

    async def _fetch_issues(self, stories: List[Story]) -> IssueList:
        state = {
            STATE_KEYS["STORIES"]: json.dumps(StoryList(stories=stories).model_dump())
        }
        agent = build_issue_agent(
            model=MODEL_ISSUE,
            tools=TOOLS["ISSUE"],
            initial_state=state,
            prompt=PROMPTS["issue"],
            debug=DEBUG,
        )
        resp = await agent.arun(
            f"Fetch details for {len(stories)} stories.", session_id=self.session_id
        )
        # log_agno_callbacks(resp, "IssueAgent", SAVE_NAME, overwrite=False)
        if not isinstance(resp.content, IssueList):
            raise TypeError("Issue agent returned wrong type")
        return resp.content

    # -------------------------------------------------------------------
    # Stage 4 – graph issues
    # -------------------------------------------------------------------
    async def _graph_issue(self, issue: Issue) -> None:
        state = {STATE_KEYS["ISSUES"]: json.dumps(issue.model_dump())}
        agent = build_graph_agent(
            model=MODEL_GRAPH,
            tools=TOOLS["GRAPH"],
            initial_state=state,
            prompt=PROMPTS["graph_issue"],
            debug=DEBUG,
        )
        graph_resp = await agent.arun(
            f"Update graph for issue {issue.story_key}.", session_id=self.session_id
        )
        # log_agno_callbacks(
        #     graph_resp, f"IssueGraph_{issue.story_key}", SAVE_NAME, overwrite=False
        # )

    # -------------------------------------------------------------------
    # Entrypoint
    # -------------------------------------------------------------------
    async def arun(self, trigger_msg: str = "Start workflow.") -> RunResponse:
        log.info("Workflow start (session_id=%s)", self.session_id)
        sem = asyncio.Semaphore(MAX_CONCURRENCY)

        # Stage 1
        epics = await self._get_epics(trigger_msg)
        log.info("Stage 1: %d epics", len(epics.epics))

        # Stage 2
        story_tasks = [
            run_with_semaphore(self._process_epic(e), sem, f"epic-{e.epic_key}")
            for e in epics.epics
        ]
        story_results = await asyncio.gather(*story_tasks)
        stories = [
            s for sub in story_results if not isinstance(sub, Exception) for s in sub
        ]
        self.session_state[STATE_KEYS["STORIES"]] = StoryList(stories=stories)
        log.info("Stage 2: %d stories", len(stories))

        # Stage 3
        graph_tasks = [
            run_with_semaphore(self._graph_story(s), sem, f"story-{s.story_key}")
            for s in stories
        ]
        issue_task = run_with_semaphore(
            self._fetch_issues(stories), sem, "fetch-issues"
        )
        issues_result, *_ = await asyncio.gather(issue_task, *graph_tasks)
        if isinstance(issues_result, Exception):
            raise issues_result
        self.session_state[STATE_KEYS["ISSUES"]] = issues_result
        log.info("Stage 3: %d issues", len(issues_result.issues))

        # Stage 4
        issue_tasks = [
            run_with_semaphore(self._graph_issue(i), sem, f"issue-{i.story_key}")
            for i in issues_result.issues
        ]
        graph_issues_resp = await asyncio.gather(*issue_tasks)

        # might report "success" even if some issue graph updates fail
        IssueGraph_failure = any(isinstance(r, Exception) for r in graph_issues_resp)
        if IssueGraph_failure:
            log.warning(
                "Encountered errors during Stage 4 (GraphIssues). Check logs for details."
            )
        log.info("Stage 4 complete")

        summary = (
            f"Processed {len(epics.epics)} epics, {len(stories)} stories, "
            f"{len(issues_result.issues)} issues."
        )
        if IssueGraph_failure:
            summary += " Some final graph updates failed."
        return RunResponse(
            content=summary, event=RunEvent.workflow_completed, run_id=self.run_id
        )


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
async def _cli():
    workflow = JiraGraphWorkflow(session_id=SESSION_ID)
    resp = await workflow.arun()
    log.info("Workflow finished: %s", resp.content)
    log_agno_callbacks(resp, "Workflow", SAVE_NAME, overwrite=False)


if __name__ == "__main__":
    asyncio.run(_cli())
