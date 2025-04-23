import sys
import asyncio
import logging
from typing import Any, List, Coroutine, Iterable

from agno.agent import Agent, RunResponse
from agno.workflow import RunEvent, Workflow

from utils.logging_setup import setup_logging
from utils.helpers import load_config, resolve_model
from models.schemas import Epic, EpicList, Story, StoryList, Issue, IssueList

from agents import (
    build_epic_agent,
    build_story_agent,
    build_issue_agent,
    build_graph_agent,
)
from tools import (
    jira_search,
    jira_get_epic_issues,
    jira_get_issue_loop,
    arango_upsert,
)


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
DEBUG = True  # Agno debugging
PROVIDER = "openai"
BATCH_SIZE = 50  # for IssueAgent


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CFG = load_config("runtime")
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
setup_logging(
    level=logging.INFO, stream=True, abort_on_log=True, abort_level=logging.ERROR
)
root_log = logging.getLogger()

# Save logs to file
file_handler = logging.FileHandler("workflow.log", mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(formatter)
root_log.addHandler(file_handler)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
async def run_with_semaphore(
    coro: Coroutine, sem: asyncio.Semaphore, label: str
) -> Any:
    """
    Utility to limit concurrency by running the coroutine under the semaphore.

    Returns either the:
     - Result of an async function
     - Error instead of crashing the gather process
    """
    async with sem:
        log.debug(f"Starting task: {label}")
        result = await coro
        log.debug(f"Finished task: {label}")
        return result


def _chunks(lst: List[Any], n: int) -> Iterable[List[Any]]:
    """
    Helper to slice lists into chunks (used for IssueAgent).
    Yields successive n-sized chunks from a list.
    """
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
class JiraGraphWorkflow(Workflow):
    """
    Fetches Jira data and updates the ArangoDB graph in async stages.
    - Inherits from Agno's Workflow class.
    - Prebuilds the EpicAGent as an attribute to save time on first call.
    """

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
        epic_state = {STATE_KEYS["EPICS"]: epic.model_dump()}

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

        # Run both agents concurrently
        _, story_resp = await asyncio.gather(graph_coro, story_coro)
        if isinstance(story_resp.content, StoryList):
            return story_resp.content.stories
        raise TypeError("Story agent returned wrong type")

    # -------------------------------------------------------------------
    # Stage 3 – graph stories & fetch issues
    # -------------------------------------------------------------------
    async def _graph_story(self, story: Story) -> None:
        story_state = {STATE_KEYS["STORIES"]: story.model_dump()}
        agent = build_graph_agent(
            model=MODEL_GRAPH,
            tools=TOOLS["GRAPH"],
            initial_state=story_state,
            prompt=PROMPTS["graph_story"],
            debug=DEBUG,
        )
        await agent.arun(
            f"Update graph for story {story.story_key}.", session_id=self.session_id
        )

    async def _fetch_issues_batched(self, stories: List[Story]) -> IssueList:
        """
        Splits the Story list into BATCH_SIZE chunks and spawns N parallel IssueAgents. Each agent now handles <= BATCH_SIZE Jira calls.
        """
        batch_tasks = []
        chunks = _chunks(stories, BATCH_SIZE)
        sem = asyncio.Semaphore(MAX_CONCURRENCY)

        for idx, chunk in enumerate(chunks, start=1):
            state = {STATE_KEYS["STORIES"]: StoryList(stories=chunk).model_dump()}
            agent = build_issue_agent(
                model=MODEL_ISSUE,
                tools=TOOLS["ISSUE"],
                initial_state=state,
                prompt=PROMPTS["issue"],
                debug=DEBUG,
            )
            label = f"issues-batch-{idx}"

            batch_tasks.append(
                run_with_semaphore(
                    agent.arun(
                        f"Fetch {len(chunk)} stories (batch {idx}).",
                        session_id=self.session_id,
                    ),
                    sem,
                    label,
                )
            )

        # Fan-out; everything runs under semaphore control
        batch_results = await asyncio.gather(*batch_tasks)

        # Keep only successful IssueLists
        issues: list[Issue] = []
        for res in batch_results:
            if isinstance(res, Exception):
                log.warning("Batch failed: %s", res)
                continue
            if not isinstance(res.content, IssueList):
                log.error("Unexpected type from IssueAgent: %s", type(res.content))
                continue
            issues.extend(res.content.issues)

        return IssueList(issues=issues)

    # -------------------------------------------------------------------
    # Stage 4 – graph issues
    # -------------------------------------------------------------------
    async def _graph_issue(self, issue: Issue) -> None:
        state = {STATE_KEYS["ISSUES"]: issue.model_dump()}
        agent = build_graph_agent(
            model=MODEL_GRAPH,
            tools=TOOLS["GRAPH"],
            initial_state=state,
            prompt=PROMPTS["graph_issue"],
            debug=DEBUG,
        )
        await agent.arun(
            f"Update graph for issue {issue.story_key}.", session_id=self.session_id
        )

    # -------------------------------------------------------------------
    # Entrypoint
    # -------------------------------------------------------------------
    async def arun(self, trigger_msg: str = "Start workflow.") -> RunResponse:
        log.info("Workflow start (session_id=%s)", self.session_id)
        sem = asyncio.Semaphore(MAX_CONCURRENCY)

        # Stage 1: Runs the EpicAgent
        epics = await self._get_epics(trigger_msg)
        log.info("Stage 1: %d epics", len(epics.epics))

        # Stage 2: Runs GraphAgent + StoryAgent instances in parallel per-epic
        story_tasks = [
            run_with_semaphore(self._process_epic(e), sem, f"epic-{e.epic_key}")
            for e in epics.epics
        ]
        story_results = await asyncio.gather(*story_tasks)

        # Flatten and store the Story results
        stories = [
            s for sub in story_results if not isinstance(sub, Exception) for s in sub
        ]
        self.session_state[STATE_KEYS["STORIES"]] = StoryList(stories=stories)
        log.info("Stage 2: %d stories", len(stories))

        # Stage 3: Runs Story GraphAgent and IssueAgent concurrently
        graph_tasks = [
            run_with_semaphore(self._graph_story(s), sem, f"story-{s.story_key}")
            for s in stories
        ]
        issue_task = run_with_semaphore(
            self._fetch_issues_batched(stories), sem, "fetch-issues"
        )
        issues_result, *_ = await asyncio.gather(issue_task, *graph_tasks)
        if isinstance(issues_result, Exception):
            raise issues_result
        self.session_state[STATE_KEYS["ISSUES"]] = issues_result
        log.info("Stage 3: %d issues", len(issues_result.issues))

        # Stage 4: Runs GraphAgent for each issue in parallel
        issue_tasks = [
            run_with_semaphore(self._graph_issue(i), sem, f"issue-{i.story_key}")
            for i in issues_result.issues
        ]
        graph_issues_resp = await asyncio.gather(*issue_tasks)

        # Might report "success" even if some graph updates fail; catch error
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

        # Final return object; triggers Agno post-processing
        return RunResponse(
            content=summary, event=RunEvent.workflow_completed, run_id=self.run_id
        )


# ---------------------------------------------------------------------------
# Run entire pipeline
# ---------------------------------------------------------------------------
async def _main():
    try:
        workflow = JiraGraphWorkflow(session_id=SESSION_ID)
        resp = await workflow.arun()
        log.info("Workflow finished: %s", resp.content)
    except Exception as e:
        log.critical("WORKFLOW ABORTED: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
