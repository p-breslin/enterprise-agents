import sys
import asyncio
import logging
import datetime
from typing import Any, List, Coroutine, Optional, Dict

from agno.agent import RunResponse
from agno.tools.mcp import MCPTools
from agno.workflow import RunEvent, Workflow

from utils.logging_setup import setup_logging
from utils.helpers import load_config, resolve_model

from models.schemas import (
    Repo,
    RepoList,
    PRNumbers,
    PRDetails,
    Commits,
    PRCommits,
)
from tools import arango_upsert
from agents.agent_factory import build_agent
from integrations.github_mcp import get_github_mcp_config


# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------
DEBUG = False
PROVIDER = "openai"
CUTOFF = {"REPO": 30, "PR": 1, "COMMIT": 5}

CFG = load_config("runtime")
MODELS = CFG["MODELS"][PROVIDER]
PROMPTS = CFG["PROMPTS"]
SESSION_PARAMS = CFG["SESSION"]
AGENT_CFGS = load_config("agents")

MAX_CONCURRENCY = SESSION_PARAMS.get("max_concurrency", 10)
SESSION_ID = SESSION_PARAMS.get("session_id", "github_graph_sync")

# Input keys for data fetching agents, for graph agents, and other inputs
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

# Define tools
TOOLS_GRAPH = [arango_upsert]

# Target GitHub Organization/User
TARGET_ORG_USER = CFG["GITHUB"]["org"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
setup_logging(
    level=logging.INFO, stream=True, abort_on_log=True, abort_level=logging.ERROR
)
root_log = logging.getLogger()

# Save logs to file
file_handler = logging.FileHandler("github_workflow.log", mode="w", encoding="utf-8")
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
    """Utility to limit concurrency and capture exceptions from coroutines."""
    async with sem:
        try:
            log.debug(f"Starting task: {label}")
            result = await coro
            log.debug(f"Finished task: {label} successfully.")
            return result
        except Exception as e:
            log.error(f"Task {label} failed: {e}", exc_info=False)
            return e


def create_pr_key(owner: str, repo: str, number: int) -> str:
    """Creates a unique string key for a PR."""
    return f"{owner}/{repo}/{number}"


# ---------------------------------------------------------------------------
# Workflow Class
# ---------------------------------------------------------------------------
class GitHubGraphWorkflow(Workflow):
    """Orchestrates fetching GitHub data and updating ArangoDB."""

    description: str = "Fetches GitHub data and updates ArangoDB graph."
    mcp_command: str
    mcp_env: Dict[str, str]

    def __init__(self, session_id: str = SESSION_ID, **kwargs):
        super().__init__(session_id=session_id, **kwargs)
        self.mcp_command, self.mcp_env = get_github_mcp_config()

    # --- Helper methods to run specific agent types ---

    async def _run_repo_agent(
        self, org_user: str, cutoff_date: str, mcp_tools: MCPTools
    ) -> Optional[RepoList]:
        """Builds and runs the RepoAgent."""
        agent_type = "RepoAgent"
        log.debug(f"Building {agent_type}...")
        try:
            agent = build_agent(
                agent_type=agent_type,
                model=resolve_model(PROVIDER, MODELS["repo"]),
                tools=[mcp_tools],
                initial_state={
                    STATE_KEYS["ORG_USER"]: org_user,
                    STATE_KEYS["CUTOFF_DATE"]: cutoff_date,
                },
                prompt_key=PROMPTS["repo"],
                response_model=True,
                debug=DEBUG,
            )
            trigger = f"Find repositories for {org_user} updated since {cutoff_date}"
            resp: RunResponse = await agent.arun(trigger, session_id=self.session_id)

            if isinstance(resp.content, RepoList):
                log.info(f"{agent_type} found {len(resp.content.repos)} repositories.")
                return resp.content
            else:
                log.error(
                    f"{agent_type} did not return RepoList. Got: {type(resp.content)}"
                )
                return None
        except Exception as e:
            log.error(f"Error running {agent_type}: {e}", exc_info=True)
            return None

    async def _run_prn_agent(
        self,
        repo_data: Repo,
        cutoff_date: str,
        mcp_tools: MCPTools,
        sem: asyncio.Semaphore,
    ) -> Optional[PRNumbers]:
        """Builds and runs PRNAgent for ONE repo using a semaphore."""
        agent_type = "PRNAgent"
        label = f"prn-{repo_data.owner}-{repo_data.repo}"

        async def task():
            log.debug(f"Building {agent_type} for {repo_data.owner}/{repo_data.repo}")
            try:
                agent = build_agent(
                    agent_type=agent_type,
                    model=resolve_model(PROVIDER, MODELS["pr"]),
                    tools=[mcp_tools],
                    initial_state={
                        STATE_KEYS["REPO_INPUT"]: repo_data.model_dump(),
                        STATE_KEYS["CUTOFF_DATE"]: cutoff_date,
                    },
                    prompt_key=PROMPTS["pr_numbers"],
                    response_model=True,
                    debug=DEBUG,
                )
                trigger = f"Find PR numbers for {repo_data.owner}/{repo_data.repo} since {cutoff_date}"
                resp: RunResponse = await agent.arun(
                    trigger, session_id=self.session_id
                )

                if isinstance(resp.content, PRNumbers):
                    log.info(
                        f"{agent_type} found {len(resp.content.pr_numbers)} PRs for {repo_data.owner}/{repo_data.repo}."
                    )
                    return resp.content
                else:
                    log.error(
                        f"{agent_type} for {repo_data.owner}/{repo_data.repo} did not return PRNumbers. Got: {type(resp.content)}"
                    )
                    return None
            except Exception as e:
                log.error(
                    f"Error running {agent_type} for {repo_data.owner}/{repo_data.repo}: {e}",
                    exc_info=True,
                )
                return None

        # Wrap the agent run logic in the semaphore
        result = await run_with_semaphore(task(), sem, label)
        return result if isinstance(result, PRNumbers) else None

    async def _run_prd_agent(
        self, pr_identifier: Dict[str, Any], mcp_tools: MCPTools, sem: asyncio.Semaphore
    ) -> Optional[PRDetails]:
        """Builds and runs PRDAgent for ONE PR number using a semaphore."""
        agent_type = "PRDAgent"
        owner, repo, number = (
            pr_identifier["owner"],
            pr_identifier["repo"],
            pr_identifier["pr_number"],
        )
        label = f"prd-{owner}-{repo}-{number}"

        async def task():
            log.debug(f"Building {agent_type} for {owner}/{repo}#{number}")
            try:
                agent = build_agent(
                    agent_type=agent_type,
                    model=resolve_model(PROVIDER, MODELS["pr"]),
                    tools=[mcp_tools],
                    initial_state={STATE_KEYS["PR_NUM_INPUT"]: pr_identifier},
                    prompt_key=PROMPTS["pr_details"],
                    response_model=True,
                    debug=DEBUG,
                )
                trigger = f"Fetch details for PR {owner}/{repo}#{number}"
                resp: RunResponse = await agent.arun(
                    trigger, session_id=self.session_id
                )

                if isinstance(resp.content, PRDetails):
                    log.info(
                        f"Successfully fetched details for PR {owner}/{repo}#{number}."
                    )
                    return resp.content
                else:
                    log.error(
                        f"{agent_type} for PR {owner}/{repo}#{number} did not return PRDetails. Got: {type(resp.content)}"
                    )
                    return None
            except Exception as e:
                log.error(
                    f"Error running {agent_type} for PR {owner}/{repo}#{number}: {e}",
                    exc_info=True,
                )
                return None

        result = await run_with_semaphore(task(), sem, label)
        return result if isinstance(result, PRDetails) else None

    async def _run_prc_agent(
        self,
        pr_details: PRDetails,
        cutoff_date: str,
        mcp_tools: MCPTools,
        sem: asyncio.Semaphore,
    ) -> Optional[PRCommits]:
        """Builds and runs PRCAgent for ONE PR using a semaphore."""
        agent_type = "PRCAgent"
        owner, repo, number = pr_details.owner, pr_details.repo, pr_details.pr_number
        label = f"prc-{owner}-{repo}-{number}"

        if not pr_details.head_sha:
            log.warning(
                f"Skipping {agent_type} for PR {owner}/{repo}#{number}: Missing head_sha."
            )
            return None

        async def task():
            log.debug(f"Building {agent_type} for {owner}/{repo}#{number}")
            try:
                agent = build_agent(
                    agent_type=agent_type,
                    model=resolve_model(PROVIDER, MODELS["pr"]),
                    tools=[mcp_tools],
                    initial_state={
                        STATE_KEYS["PR_DETAILS_INPUT"]: pr_details.model_dump(),
                        STATE_KEYS["CUTOFF_DATE"]: cutoff_date,
                    },
                    prompt_key=PROMPTS["pr_commits"],
                    response_model=True,
                    debug=DEBUG,
                )
                trigger = f"Fetch commits for PR {owner}/{repo}#{number} (head: {pr_details.head_sha[:7]}) since {cutoff_date}"
                resp: RunResponse = await agent.arun(
                    trigger, session_id=self.session_id
                )

                if isinstance(resp.content, PRCommits):
                    log.info(
                        f"{agent_type} found {len(resp.content.commits)} commits for PR {owner}/{repo}#{number}."
                    )
                    return resp.content
                else:
                    log.error(
                        f"{agent_type} for PR {owner}/{repo}#{number} did not return PRCommits. Got: {type(resp.content)}"
                    )
                    return None
            except Exception as e:
                log.error(
                    f"Error running {agent_type} for PR {owner}/{repo}#{number}: {e}",
                    exc_info=True,
                )
                return None

        result = await run_with_semaphore(task(), sem, label)
        return result if isinstance(result, PRCommits) else None

    async def _run_graph_repo(self, repo_data: Repo, sem: asyncio.Semaphore) -> bool:
        """Graphs a single Repository."""
        agent_type = "GraphAgent"
        label = f"graph-repo-{repo_data.owner}-{repo_data.repo}"

        async def task():
            log.debug(
                f"Building {agent_type} for Repo {repo_data.owner}/{repo_data.repo}"
            )
            try:
                agent = build_agent(
                    agent_type=agent_type,
                    model=resolve_model(PROVIDER, MODELS["graph"]),
                    tools=TOOLS_GRAPH,
                    initial_state={
                        STATE_KEYS["REPO_GRAPH_INPUT"]: repo_data.model_dump()
                    },
                    prompt_key=PROMPTS["repo_graph"],
                    response_model=False,
                    debug=DEBUG,
                )
                trigger = (
                    f"Update graph for repository {repo_data.owner}/{repo_data.repo}."
                )
                await agent.arun(trigger, session_id=self.session_id)
                log.info(
                    f"GraphAgent sequence initiated successfully for Repo {repo_data.owner}/{repo_data.repo}."
                )
                return True
            except Exception as e:
                log.error(
                    f"Error running GraphAgent for Repo {repo_data.owner}/{repo_data.repo}: {e}",
                    exc_info=True,
                )
                return False

        result = await run_with_semaphore(task(), sem, label)
        return result is True

    async def _run_graph_pr(
        self, pr_details: PRDetails, sem: asyncio.Semaphore
    ) -> bool:
        """Graphs a single Pull Request based on its details."""
        agent_type = "GraphAgent"
        owner, repo, number = pr_details.owner, pr_details.repo, pr_details.pr_number
        label = f"graph-pr-{owner}-{repo}-{number}"

        async def task():
            log.debug(f"Building {agent_type} for PR {owner}/{repo}#{number}")
            try:
                agent = build_agent(
                    agent_type=agent_type,
                    model=resolve_model(PROVIDER, MODELS["graph"]),
                    tools=TOOLS_GRAPH,
                    initial_state={
                        STATE_KEYS["PR_GRAPH_INPUT"]: pr_details.model_dump()
                    },
                    prompt_key=PROMPTS["pr_graph"],
                    response_model=False,
                    debug=DEBUG,
                )
                trigger = f"Update graph for pull request {owner}/{repo}#{number}."
                await agent.arun(trigger, session_id=self.session_id)
                log.info(
                    f"GraphAgent sequence initiated successfully for PR {owner}/{repo}#{number}."
                )
                return True
            except Exception as e:
                log.error(
                    f"Error running GraphAgent for PR {owner}/{repo}#{number}: {e}",
                    exc_info=True,
                )
                return False

        result = await run_with_semaphore(task(), sem, label)
        return result is True

    async def _run_graph_commit(
        self, commit_data: Commits, pr_context: Dict[str, Any], sem: asyncio.Semaphore
    ) -> bool:
        """Graphs a single Commit, ensuring PR context (owner, repo, number) is included."""
        agent_type = "GraphAgent"
        sha_short = commit_data.sha[:7]
        owner, repo, number = (
            pr_context["owner"],
            pr_context["repo"],
            pr_context["pr_number"],
        )
        label = f"graph-commit-{owner}-{repo}-{number}-{sha_short}"

        # Combine commit data with the necessary PR context
        graph_commit_input = {
            **commit_data.model_dump(),
            "owner": owner,
            "repo": repo,
            "pr_number": number,
        }

        async def task():
            log.debug(
                f"Building {agent_type} for Commit {sha_short} (PR {owner}/{repo}#{number})"
            )
            try:
                agent = build_agent(
                    agent_type=agent_type,
                    model=resolve_model(PROVIDER, MODELS["graph"]),
                    tools=TOOLS_GRAPH,
                    initial_state={
                        STATE_KEYS["COMMIT_GRAPH_INPUT"]: graph_commit_input
                    },
                    prompt_key=PROMPTS["commit_graph"],
                    response_model=False,
                    debug=DEBUG,
                )
                trigger = f"Update graph for commit {sha_short} associated with PR {owner}/{repo}#{number}."
                await agent.arun(trigger, session_id=self.session_id)
                log.info(
                    f"GraphAgent sequence initiated successfully for Commit {sha_short}."
                )
                return True
            except Exception as e:
                log.error(
                    f"Error running GraphAgent for Commit {sha_short}: {e}",
                    exc_info=True,
                )
                return False

        result = await run_with_semaphore(task(), sem, label)
        return result is True

    # --- Main Workflow Orchestration ---
    async def arun(
        self, trigger_msg: Optional[str] = None, cutoff: Dict = CUTOFF
    ) -> RunResponse:
        """Executes the full GitHub to ArangoDB graph workflow."""
        start_time = datetime.datetime.now()
        log.info(f"Workflow start (session_id={self.session_id})")
        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        final_event = RunEvent.workflow_completed
        error_messages = []

        # Cutoff dates
        cutoff_repo = (
            datetime.date.today() - datetime.timedelta(days=cutoff["REPO"])
        ).strftime("%Y-%m-%d")

        cutoff_pr = (
            datetime.date.today() - datetime.timedelta(days=cutoff["PR"])
        ).strftime("%Y-%m-%d")

        cutoff_commits = (
            datetime.date.today() - datetime.timedelta(days=cutoff["REPO"])
        ).strftime("%Y-%m-%d")

        # --- Stats ---
        repo_count = 0
        repo_graph_success_count = 0
        pr_identifier_count = 0
        pr_detail_fetch_success_count = 0
        pr_graph_success_count = 0
        pr_commit_fetch_success_count = 0
        commit_graph_success_count = 0
        total_commits_processed = 0

        # --- Data Stores ---
        repos: List[Repo] = []
        unique_pr_identifiers: List[Dict[str, Any]] = []
        prd_dict: Dict[str, PRDetails] = {}
        prc_dict: Dict[str, PRCommits] = {}

        async with MCPTools(self.mcp_command, env=self.mcp_env) as mcp_tools:
            log.info("GitHub MCP Server connected successfully.")

            # === Stage 1: Fetch Repositories ===
            log.info("--- Stage 1: Fetching Repositories ---")
            repo_list_obj = await self._run_repo_agent(
                TARGET_ORG_USER, cutoff_repo, mcp_tools
            )
            if not repo_list_obj:
                error_messages.append("Failed to fetch initial repository list.")
                final_event = RunEvent.workflow_failed
                log.critical("Workflow terminated: Cannot fetch repositories.")
                return RunResponse(
                    content=". ".join(error_messages),
                    event=final_event,
                    run_id=self.run_id,
                )
            repos = repo_list_obj.repos
            repo_count = len(repos)
            log.info(f"Stage 1 Completed: Found {repo_count} relevant repositories.")

            # === Stage 1.5: Graph Repositories (Parallel per Repo) ===
            if repos:
                log.info(
                    f"--- Stage 1.5: Graphing {repo_count} Repositories (Concurrency: {MAX_CONCURRENCY}) ---"
                )
                graph_repo_tasks = [self._run_graph_repo(repo, sem) for repo in repos]
                graph_repo_results = await asyncio.gather(*graph_repo_tasks)
                repo_graph_success_count = sum(
                    1 for res in graph_repo_results if res is True
                )
                log.info(
                    f"Stage 1.5 Completed: Successfully initiated graph updates for {repo_graph_success_count}/{repo_count} repos."
                )
                if repo_graph_success_count < repo_count:
                    final_event = RunEvent.workflow_completed_with_errors
                    error_messages.append(
                        f"Failed to initiate graph updates for {repo_count - repo_graph_success_count} repos."
                    )

            # === Stage 2: Fetch Relevant PR Numbers (Parallel per Repo) ===
            log.info(
                f"--- Stage 2: Fetching PR Numbers for {repo_count} Repos (Concurrency: {MAX_CONCURRENCY}) ---"
            )
            prn_tasks = [
                self._run_prn_agent(repo, cutoff_pr, mcp_tools, sem) for repo in repos
            ]
            prn_results = await asyncio.gather(*prn_tasks)

            # Aggregate results into unique_pr_identifier
            all_pr_identifiers = []

            for result in prn_results:
                if isinstance(result, PRNumbers):
                    for number in result.pr_numbers:
                        all_pr_identifiers.append(
                            {
                                "owner": result.owner,
                                "repo": result.repo,
                                "pr_number": number,
                            }
                        )
                elif isinstance(result, Exception):
                    error_messages.append(
                        f"Fetching PR numbers failed for a repo: {result}"
                    )
            unique_pr_identifiers = [
                dict(t) for t in {tuple(d.items()) for d in all_pr_identifiers}
            ]
            pr_identifier_count = len(unique_pr_identifiers)
            log.info(
                f"Stage 2 Completed: Found {pr_identifier_count} unique relevant PR identifiers."
            )
            if not unique_pr_identifiers and repo_count > 0:
                log.warning("No relevant PRs found to process further.")

            # === Stage 3: Fetch PR Details (Parallel per PR Number) ===
            if unique_pr_identifiers:
                log.info(
                    f"--- Stage 3: Fetching PR Details for {pr_identifier_count} PRs (Concurrency: {MAX_CONCURRENCY}) ---"
                )
                prd_tasks = [
                    self._run_prd_agent(pr_id, mcp_tools, sem)
                    for pr_id in unique_pr_identifiers
                ]
                prd_results = await asyncio.gather(*prd_tasks)

                # Populate prd_dict
                for result in prd_results:
                    if isinstance(result, PRDetails):
                        key = create_pr_key(result.owner, result.repo, result.pr_number)
                        prd_dict[key] = result
                    elif isinstance(result, Exception):
                        error_messages.append(
                            f"Fetching PR details failed for a PR: {result}"
                        )
                pr_detail_fetch_success_count = len(prd_dict)
                log.info(
                    f"Stage 3 Completed: Successfully fetched details for {pr_detail_fetch_success_count}/{pr_identifier_count} PRs."
                )

            # === Stage 3.5: Graph PRs (Parallel per PR Detail) ===
            if prd_dict:
                log.info(
                    f"--- Stage 3.5: Graphing {pr_detail_fetch_success_count} PRs (Concurrency: {MAX_CONCURRENCY}) ---"
                )
                graph_pr_tasks = [
                    self._run_graph_pr(pr_detail, sem)
                    for pr_detail in prd_dict.values()
                ]
                graph_pr_results = await asyncio.gather(*graph_pr_tasks)
                pr_graph_success_count = sum(
                    1 for res in graph_pr_results if res is True
                )
                log.info(
                    f"Stage 3.5 Completed: Successfully initiated graph updates for {pr_graph_success_count}/{pr_detail_fetch_success_count} PRs."
                )
                if pr_graph_success_count < pr_detail_fetch_success_count:
                    final_event = RunEvent.workflow_completed_with_errors
                    error_messages.append(
                        f"Failed to initiate graph updates for {pr_detail_fetch_success_count - pr_graph_success_count} PRs."
                    )

            # === Stage 4: Fetch PR Commits (Parallel per PR with Details) ===
            if prd_dict:
                log.info(
                    f"--- Stage 4: Fetching PR Commits for {pr_detail_fetch_success_count} PRs (Concurrency: {MAX_CONCURRENCY}) ---"
                )
                prc_tasks = [
                    self._run_prc_agent(prd, cutoff_commits, mcp_tools, sem)
                    for prd in prd_dict.values()
                ]
                prc_results = await asyncio.gather(*prc_tasks)

                # Populate prc_dict
                for result in prc_results:
                    if isinstance(result, PRCommits):
                        key = create_pr_key(result.owner, result.repo, result.pr_number)
                        prc_dict[key] = result
                    elif isinstance(result, Exception):
                        error_messages.append(
                            f"Fetching PR commits failed for a PR: {result}"
                        )
                pr_commit_fetch_success_count = len(prc_dict)
                log.info(
                    f"Stage 4 Completed: Successfully fetched commits for {pr_commit_fetch_success_count} PRs."
                )

            # === Stage 4.5: Graph Commits (Parallel per individual Commit) ===
            if prc_dict:
                log.info(
                    f"--- Stage 4.5: Graphing Commits from {pr_commit_fetch_success_count} PRs (Concurrency: {MAX_CONCURRENCY}) ---"
                )
                graph_commit_tasks = []
                for pr_key, pr_commits_obj in prc_dict.items():
                    # Need owner/repo/number context for each commit graph task
                    pr_context = {
                        "owner": pr_commits_obj.owner,
                        "repo": pr_commits_obj.repo,
                        "pr_number": pr_commits_obj.pr_number,
                    }
                    total_commits_processed += len(pr_commits_obj.commits)
                    for commit in pr_commits_obj.commits:
                        graph_commit_tasks.append(
                            self._run_graph_commit(commit, pr_context, sem)
                        )

                if graph_commit_tasks:
                    log.info(
                        f"Initiating graph updates for {total_commits_processed} total commits."
                    )
                    graph_commit_results = await asyncio.gather(*graph_commit_tasks)
                    commit_graph_success_count = sum(
                        1 for res in graph_commit_results if res is True
                    )
                    log.info(
                        f"Stage 4.5 Completed: Successfully initiated graph updates for {commit_graph_success_count}/{total_commits_processed} commits."
                    )
                    if commit_graph_success_count < total_commits_processed:
                        final_event = RunEvent.workflow_completed_with_errors
                        error_messages.append(
                            f"Failed to initiate graph updates for {total_commits_processed - commit_graph_success_count} commits."
                        )
                else:
                    log.info("Stage 4.5: No commits found to graph.")

        # --- Workflow Finalization ---
        end_time = datetime.datetime.now()
        duration = end_time - start_time
        log.info(
            f"Workflow finished (session_id={self.session_id}). Duration: {duration}"
        )

        summary = (
            f"Completed GitHub sync. "
            f"Repos: {repo_count} (graph success: {repo_graph_success_count}). "
            f"PR IDs: {pr_identifier_count}. "
            f"PR Details: {pr_detail_fetch_success_count} (graph success: {pr_graph_success_count}). "
            f"PR Commits Fetched: {pr_commit_fetch_success_count}. "
            f"Total Commits: {total_commits_processed} (graph success: {commit_graph_success_count})."
        )

        if error_messages:
            summary += f" Encountered {len(error_messages)} errors during fetch/graph initiation. Check logs."
            log.warning("Workflow completed with errors. Summary of issues:")
            for err in error_messages[:5]:
                log.warning(f"- {err}")

        return RunResponse(
            content=summary,
            event=final_event,
            run_id=self.run_id,
            metrics={"duration_seconds": duration.total_seconds()},
        )


# ---------------------------------------------------------------------------
# Main Execution Block
# ---------------------------------------------------------------------------
async def main():
    """Runs the GitHub to Graph workflow."""
    log.info(f"Initializing GitHubGraphWorkflow with session ID: {SESSION_ID}")
    workflow = GitHubGraphWorkflow(session_id=SESSION_ID)

    log.info("Running workflow...")
    try:
        final_response = await workflow.arun(cutoff=CUTOFF)
        log.info(f"Workflow Final Status: {final_response.event}")
        log.info(f"Workflow Final Message: {final_response.content}")
        if final_response.metrics:
            log.info(f"Workflow Metrics: {final_response.metrics}")

    except Exception:
        log.critical(
            "Workflow execution failed with unhandled exception!", exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
