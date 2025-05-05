"""
Pipeline to sync a GitHub organisation into an ArangoDB graph.

Stages:
1. RepoAgent -> list repos + graph each repo
2. PRNAgent (fans-out) -> list PR numbers per repo
3. PRDAgent (fans-out) -> fetch PR details + graph each PR
4. PRCAgent (fans-out) -> fetch commits per PR + graph each commit

Graph stages are blocking: repo_graph must finish before pr_graph, pr_graph must finish before commit_graph.
"""

from __future__ import annotations

import sys
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
)

from agno.agent import RunResponse
from agno.workflow import RunEvent, Workflow

from utils.logging_setup import setup_logging
from utils.helpers import load_config, resolve_model

from models.schemas import Repo, RepoList, PRNumbers, PRDetails, PRCommits
from tools import arango_upsert
from tools.tools_github import (
    list_commits,
    get_pull_request,
    get_pull_request_status,
    get_pull_request_reviews,
    get_pull_request_files,
    search_issues,
    search_repositories,
)
from agents.agent_factory import build_agent

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
CFG = load_config("runtime")
PROVIDER = "openai"
MODELS = CFG["MODELS"][PROVIDER]
PROMPTS = CFG["PROMPTS"]
SESSION_PARAMS = CFG["SESSION"]
TARGET_ORG_USER = CFG["GITHUB"]["org"]

MAX_CONCURRENCY = SESSION_PARAMS.get("max_concurrency", 10)
SESSION_ID = SESSION_PARAMS.get("session_id", "github_graph_sync")

CUTOFF_DEFAULT: Mapping[str, int] = {"REPO": 3, "PR": 1, "COMMIT": 5}

STATE_KEYS = {
    "REPO_INPUT": "input_repo_data",
    "PR_NUM_INPUT": "input_pr_number_data",
    "PR_DETAILS_INPUT": "input_pr_details_data",
    "REPO_GRAPH_INPUT": "repo_data_input",
    "PR_GRAPH_INPUT": "pr_details_data_input",
    "COMMIT_GRAPH_INPUT": "commit_data_input",
    "CUTOFF_DATE": "cutoff_date",
    "ORG_USER": "org_or_user",
}

TOOLS: Dict[str, Sequence[Callable[..., Any]]] = {
    "graph": [arango_upsert],
    "repo_fetch": [search_repositories],
    "pr_num_fetch": [search_issues],
    "pr_details_fetch": [
        get_pull_request,
        get_pull_request_status,
        get_pull_request_reviews,
        get_pull_request_files,
    ],
    "pr_commit_fetch": [list_commits],
}

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
setup_logging(level=logging.INFO, stream=True)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------------------------
T = TypeVar("T")


async def limited(
    coro: Coroutine[Any, Any, T],
    sem: asyncio.Semaphore,
    label: str,
) -> Optional[T]:
    """
    Run coro under sem. Log exceptions and return `None` on failure.
        1.  Waits for a slot in the semaphore (respects MAX_CONCURRENCY).
        2.	Catches exceptions, logs them, and turns them into None.
    Note that swallowing errors (returning None) lets the workflow continue rather than crash.
    """
    async with sem:
        try:
            log.debug("Running task %s", label)
            return await coro
        except Exception:
            log.exception("Task %s failed", label)
            return None


# ------------------------------------------------------------------------------
# Cached agent runner
# ------------------------------------------------------------------------------
class AgentRunner:
    """
    Builds and caches agents per agent_type; executes them with varying state.
    Idea is to build an Agno agent once, then reuse it for every repo/PR/commit.
    """

    def __init__(
        self,
        provider: str,
        models: Mapping[str, str],
        prompts: Mapping[str, str],
    ) -> None:
        self._provider = provider
        self._models = models
        self._prompts = prompts
        self._cache: Dict[str, Any] = {}

    async def _execute(
        self,
        agent_type: str,
        model_key: str,
        prompt_key: str,
        tools: Sequence[Callable[..., Any]],
        initial_state: Dict[str, Any],
        trigger: str,
        expect: type[T],
    ) -> Optional[T]:
        agent = self._cache.get(agent_type)
        if agent is None:
            agent = build_agent(
                agent_type=agent_type,
                model=resolve_model(self._provider, self._models[model_key]),
                tools=list(tools),
                initial_state={},
                prompt_key=self._prompts[prompt_key],
                response_model=True,
            )
            self._cache[agent_type] = agent

        agent.initial_state.update(initial_state)
        resp: RunResponse = await agent.arun(trigger, session_id=SESSION_ID)
        return resp.content if isinstance(resp.content, expect) else None

    async def run(
        self,
        *,
        agent_type: str,
        model_key: str,
        prompt_key: str,
        tools: Sequence[Callable[..., Any]],
        initial_state: Dict[str, Any],
        trigger: str,
        expect: type[T],
        sem: asyncio.Semaphore,
        label: str,
    ) -> Optional[T]:
        """
        Wraps _execute with the limited helper so that the concurrency cap is respected.
        """
        return await limited(
            self._execute(
                agent_type,
                model_key,
                prompt_key,
                tools,
                initial_state,
                trigger,
                expect,
            ),
            sem,
            label,
        )


# ------------------------------------------------------------------------------
# Workflow
# ------------------------------------------------------------------------------
class GitHubGraphWorkflow(Workflow):
    description = "Fetch GitHub data and update ArangoDB graph."

    def __init__(self, session_id: str = SESSION_ID) -> None:
        super().__init__(session_id=session_id)
        self.sem = asyncio.Semaphore(MAX_CONCURRENCY)
        self.runner = AgentRunner(PROVIDER, MODELS, PROMPTS)

    # Stage helpers ------------------------------------------------------------
    async def fetch_repos(self, cutoff: str) -> List[Repo]:
        result = await self.runner.run(
            agent_type="RepoAgent",
            model_key="repo",
            prompt_key="repo",
            tools=TOOLS["repo_fetch"],
            initial_state={
                STATE_KEYS["ORG_USER"]: TARGET_ORG_USER,
                STATE_KEYS["CUTOFF_DATE"]: cutoff,
            },
            trigger=f"Find repositories for {TARGET_ORG_USER} updated since {cutoff}",
            expect=RepoList,
            sem=self.sem,
            label="RepoAgent",
        )
        return result.repos if result else []

    async def fetch_pr_numbers(self, repo: Repo, cutoff: str) -> List[int]:
        label = f"PRNAgent:{repo.owner}/{repo.repo}"
        result = await self.runner.run(
            agent_type="PRNAgent",
            model_key="pr",
            prompt_key="pr_numbers",
            tools=TOOLS["pr_num_fetch"],
            initial_state={
                STATE_KEYS["REPO_INPUT"]: repo.model_dump(),
                STATE_KEYS["CUTOFF_DATE"]: cutoff,
            },
            trigger=f"Find PR numbers for {repo.owner}/{repo.repo} since {cutoff}",
            expect=PRNumbers,
            sem=self.sem,
            label=label,
        )
        return result.pr_numbers if result else []

    async def fetch_pr_details(self, pr_id: Dict[str, Any]) -> Optional[PRDetails]:
        label = f"PRDAgent:{pr_id['owner']}/{pr_id['repo']}#{pr_id['pr_number']}"
        return await self.runner.run(
            agent_type="PRDAgent",
            model_key="pr",
            prompt_key="pr_details",
            tools=TOOLS["pr_details_fetch"],
            initial_state={STATE_KEYS["PR_NUM_INPUT"]: pr_id},
            trigger=f"Fetch details for {label}",
            expect=PRDetails,
            sem=self.sem,
            label=label,
        )

    async def fetch_pr_commits(self, pr: PRDetails, cutoff: str) -> Optional[PRCommits]:
        if not pr.head_sha:
            log.warning(
                "Skipping commits for %s/%s#%s - missing head_sha",
                pr.owner,
                pr.repo,
                pr.pr_number,
            )
            return None
        label = f"PRCAgent:{pr.owner}/{pr.repo}#{pr.pr_number}"
        return await self.runner.run(
            agent_type="PRCAgent",
            model_key="pr",
            prompt_key="pr_commits",
            tools=TOOLS["pr_commit_fetch"],
            initial_state={
                STATE_KEYS["PR_DETAILS_INPUT"]: pr.model_dump(),
                STATE_KEYS["CUTOFF_DATE"]: cutoff,
            },
            trigger=f"Fetch commits for {label}",
            expect=PRCommits,
            sem=self.sem,
            label=label,
        )

    # Graph upsert helpers -----------------------------------------------------
    async def _graph_execute(
        self, prompt_key: str, state_key: str, data: Dict[str, Any]
    ) -> bool:
        agent = build_agent(
            agent_type="GraphAgent",
            model=resolve_model(PROVIDER, MODELS["graph"]),
            tools=TOOLS["graph"],
            initial_state={state_key: data},
            prompt_key=PROMPTS[prompt_key],
            response_model=False,
        )
        await agent.arun("graph-upsert", session_id=self.session_id)
        return True

    async def graph_update(
        self, *, prompt_key: str, state_key: str, data: Dict[str, Any], label: str
    ) -> bool:
        return bool(
            await limited(
                self._graph_execute(prompt_key, state_key, data),
                self.sem,
                f"Graph:{label}",
            )
        )

    # Orchestrator -------------------------------------------------------------
    async def arun(self, *, cutoff: Mapping[str, int] = CUTOFF_DEFAULT) -> RunResponse:
        t0 = datetime.utcnow()
        log.info("Workflow start  session=%s", self.session_id)

        cutoff_repo = (date.today() - timedelta(days=cutoff["REPO"])).isoformat()
        cutoff_pr = (date.today() - timedelta(days=cutoff["PR"])).isoformat()
        cutoff_commit = (date.today() - timedelta(days=cutoff["COMMIT"])).isoformat()

        # --- Stage 1 ---
        repos = await self.fetch_repos(cutoff_repo)
        if not repos:
            log.warning("No repos found - aborting.")
            return RunResponse(
                "No updated repos.", RunEvent.workflow_completed, self.run_id
            )

        # repo_graph must complete before moving on
        repo_graph_tasks = [
            self.graph_update(
                prompt_key="repo_graph",
                state_key=STATE_KEYS["REPO_GRAPH_INPUT"],
                data=repo.model_dump(),
                label=f"{repo.owner}/{repo.repo}",
            )
            for repo in repos
        ]
        await asyncio.gather(*repo_graph_tasks)
        log.info("Repo graph updates complete.")

        # --- Stage 2 ---
        prn_tasks = [self.fetch_pr_numbers(repo, cutoff_pr) for repo in repos]
        pr_number_lists = await asyncio.gather(*prn_tasks)

        # flatten
        pr_ids: List[Dict[str, Any]] = []
        for repo, numbers in zip(repos, pr_number_lists):
            pr_ids += [
                {"owner": repo.owner, "repo": repo.repo, "pr_number": n}
                for n in numbers
            ]

        if not pr_ids:
            log.warning("No PR numbers found. Nothing more to do.")
            return RunResponse(
                "Repos updated; no PRs.", RunEvent.workflow_completed, self.run_id
            )

        # --- Stage 3 ---
        prd_tasks = [self.fetch_pr_details(pid) for pid in pr_ids]
        pr_details_raw = await asyncio.gather(*prd_tasks)
        pr_details = [prd for prd in pr_details_raw if prd]

        pr_graph_tasks = [
            self.graph_update(
                prompt_key="pr_graph",
                state_key=STATE_KEYS["PR_GRAPH_INPUT"],
                data=prd.model_dump(),
                label=f"{prd.owner}/{prd.repo}#{prd.pr_number}",
            )
            for prd in pr_details
        ]
        await asyncio.gather(*pr_graph_tasks)
        log.info("PR graph updates complete.")

        # --- Stage 4 ---
        prc_tasks = [self.fetch_pr_commits(prd, cutoff_commit) for prd in pr_details]
        prc_results = await asyncio.gather(*prc_tasks)
        pr_commits_objs = [obj for obj in prc_results if obj]

        commit_graph_tasks: List[Coroutine[Any, Any, bool]] = []
        total_commits = 0
        for prc in pr_commits_objs:
            total_commits += len(prc.commits)
            for commit in prc.commits:
                commit_graph_tasks.append(
                    self.graph_update(
                        prompt_key="commit_graph",
                        state_key=STATE_KEYS["COMMIT_GRAPH_INPUT"],
                        data={
                            **commit.model_dump(),
                            "owner": prc.owner,
                            "repo": prc.repo,
                            "pr_number": prc.pr_number,
                        },
                        label=f"{commit.sha[:7]} ({prc.repo}#{prc.pr_number})",
                    )
                )
        if commit_graph_tasks:
            await asyncio.gather(*commit_graph_tasks)
        log.info("Commit graph updates complete.")

        duration = (datetime.utcnow() - t0).total_seconds()
        summary = (
            f"Repos {len(repos)}  | "
            f"PRs {len(pr_details)}  | "
            f"Commits {total_commits}\n"
            f"Elapsed {duration:.1f}s"
        )

        return RunResponse(
            content=summary,
            event=RunEvent.workflow_completed,
            run_id=self.run_id,
            metrics={"duration_seconds": duration},
        )


# ------------------------------------------------------------------------------
# Entry‑point
# ------------------------------------------------------------------------------
async def main() -> None:
    workflow = GitHubGraphWorkflow(SESSION_ID)
    resp = await workflow.arun()
    log.info("Finished: %s", resp.content)
    if resp.event != RunEvent.workflow_completed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
