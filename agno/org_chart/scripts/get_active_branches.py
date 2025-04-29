import os
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv
from github import Github, GithubException
from utils.logging_setup import setup_logging
from datetime import datetime, timedelta, timezone


load_dotenv()
setup_logging()
log = logging.getLogger(__name__)

CUTOFF = datetime.now(timezone.utc) - timedelta(days=30)
CONCURRENCY = 20  # max parallel calls


def iso_to_utc(ts: str) -> datetime:
    """2024-03-01T12:34:56Z -> timezone-aware UTC datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


async def fetch_commit_date(
    session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore
) -> datetime:
    """Returns the committer date for one commit API URL."""
    async with sem:  # throttle to CONCURRENCY
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()

    ts = data["commit"]["committer"]["date"] or data["commit"]["author"]["date"]
    return iso_to_utc(ts)


async def active_branches_async(repo_slug: str, concurrency: int):
    """Finds branch names whose tip commit is newer than CUTOFF."""
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    gh = Github(token)

    # Get repo & branches (blocking, but only one API call)
    try:
        repo = gh.get_repo(repo_slug)
        log.info("Opened %s", repo_slug)
    except GithubException as exc:
        raise SystemExit(f"GitHub error: {exc.data.get('message', exc)}")

    branches = list(repo.get_branches())  # PyGithub paginates automatically
    log.info("Found %d branches", len(branches))

    # commit URLs are already in the raw branch payload ─ no extra cost here
    commit_endpoints = [br.raw_data["commit"]["url"] for br in branches]

    # async fetch of commit metadata
    headers = {"Authorization": f"token {token}"}
    semaphore = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [
            asyncio.create_task(fetch_commit_date(session, url, semaphore))
            for url in commit_endpoints
        ]
        dates = await asyncio.gather(*tasks, return_exceptions=True)

    # filter by cutoff while skipping any failed fetches
    active = []
    for br, date in zip(branches, dates):
        if isinstance(date, datetime):
            if date >= CUTOFF:
                log.info("Active: Branch %-30s  date %s", br.name, date)
                active.append(br.name)
            else:
                log.info("Inactive: Branch %-30s  date %s", br.name, date)
        else:
            log.warning("Failed to fetch commit for %s: %s", br.name, date)

    return active


branches = sorted(
    asyncio.run(active_branches_async(repo_slug="omantra/om", concurrency=CONCURRENCY))
)

if branches:
    print("Active branches:")
    for b in branches:
        print(f"    - {b}")
else:
    print("No branches updated in the last 30 days.")


def list_branches():
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    gh = Github(token)
    repo = gh.get_repo("omantra/om")
    branches = list(repo.get_branches())
    for b in branches:
        print(b.name)
