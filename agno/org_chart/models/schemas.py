from pydantic import BaseModel, Field
from typing import Optional, List, Union


# --------------------------------------------------------------------
# Jira models
# --------------------------------------------------------------------


class Epic(BaseModel):
    epic_key: str = Field(description="Unique key of the epic")
    epic_summary: str = Field(description="Title or summary of the epic")
    project: str = Field(description="The project this epic belongs to")


class EpicList(BaseModel):
    epics: List[Epic]


class Story(BaseModel):
    story_key: str = Field(description="Unique key of the story")
    epic_key: str = Field(description="Key of the parent epic")


class StoryList(BaseModel):
    stories: List[Story]


class Issue(BaseModel):
    story_key: str
    epic_key: Optional[str]
    summary: str
    status: str
    issuetype: str
    assignee: Optional[str]
    reporter: Optional[str]
    created: str
    updated: str
    resolutiondate: Optional[str]
    resolution: Optional[str]
    priority: str
    project: str
    sprint: Optional[str]
    team: Optional[str]
    issue_size: Optional[str]
    story_points: Optional[Union[float, int]]


class IssueList(BaseModel):
    issues: List[Issue]


# --------------------------------------------------------------------
# GitHub models
# --------------------------------------------------------------------


class Repo(BaseModel):
    """A GitHub repository entry produced by RepoAgent."""

    owner: str = Field(description="GitHub username or organisation")
    repo: str = Field(description="Repository name")
    default_branch: Optional[str] = Field(
        default=None, description="Default branch name (e.g. 'main')"
    )
    visibility: Optional[str] = Field(default=None, description="'public' or 'private'")
    updated_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp of last update (push)"
    )


class RepoList(BaseModel):
    repos: List[Repo]


class PullRequest(BaseModel):
    """A pull-request entry produced by PRAgent."""

    owner: str
    repo: str
    pr_number: int = Field(description="Pull request number")
    title: Optional[str]
    state: Optional[str] = Field(description="open / closed / merged", default=None)
    created_at: Optional[str]
    updated_at: Optional[str]
    head_sha: Optional[str] = Field(
        default=None, description="Current HEAD SHA of the PR"
    )
    user: Optional[str] = Field(default=None, description="Author username")
    base_branch: Optional[str]


class PullRequestList(BaseModel):
    pull_requests: List[PullRequest]


class Review(BaseModel):
    """A review on a PR, produced by ReviewAgent."""

    owner: str
    repo: str
    pr_number: int
    reviewer: str
    state: str = Field(description="APPROVED / CHANGES_REQUESTED / COMMENTED")
    submitted_at: str
    body: Optional[str]
    commit_id: Optional[str]


class ReviewList(BaseModel):
    reviews: List[Review]


class Commit(BaseModel):
    """A commit belonging to a PR, produced by CommitAgent."""

    owner: str
    repo: str
    pr_number: int
    sha: str = Field(description="40-char commit SHA")
    author: Optional[str]
    message: str
    date: str = Field(description="Commit timestamp (ISO-8601)")
    files_changed: Optional[int]
    additions: Optional[int]
    deletions: Optional[int]


class CommitList(BaseModel):
    commits: List[Commit]
