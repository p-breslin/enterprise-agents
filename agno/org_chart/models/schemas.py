from pydantic import BaseModel, Field
from typing import Optional, List, Union


# ------------------------------------------------------------------------------
# Jira models
# ------------------------------------------------------------------------------


# Basic info about org Epics ---------------------------------------------------
class Epic(BaseModel):
    epic_key: str = Field(description="Unique key of the epic")
    epic_summary: str = Field(description="Title or summary of the epic")
    project: str = Field(description="The project this epic belongs to")


class EpicList(BaseModel):
    epics: List[Epic]


# Story keys for each Epic -----------------------------------------------------
class Story(BaseModel):
    story_key: str = Field(description="Unique key of the story")
    epic_key: str = Field(description="Key of the parent epic")


class StoryList(BaseModel):
    stories: List[Story]


# Additional detail for each Story ---------------------------------------------
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


# ------------------------------------------------------------------------------
# GitHub models
# ------------------------------------------------------------------------------


# Basic org repositories search ------------------------------------------------
class Repo(BaseModel):
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


# Pull-request numbers ---------------------------------------------------------
class PRDiscovery(BaseModel):
    owner: str = Field(description="Repository owner (user or org)")
    repo: str = Field(description="Repository name")
    relevant_pr_numbers: List[int] = Field(
        description="List of PR numbers updated since the specified cutoff time"
    )


# Pull-request entry -----------------------------------------------------------
class PREnrichment(BaseModel):
    owner: str = Field(description="Repository owner (user or org)")
    repo: str = Field(description="Repository name")
    pr_number: int = Field(description="Pull request number within the repository")
    title: Optional[str] = Field(default=None, description="Title of the pull request")
    body: Optional[str] = Field(
        default=None,
        description="Body/description of the pull request (may require get_pull_request for full content)",
    )
    state: Optional[str] = Field(
        default=None, description="State of the pull request (e.g., 'open', 'closed')"
    )
    created_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when the PR was created"
    )
    updated_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when the PR was last updated"
    )
    closed_at: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp when the PR was closed (if not merged)",
    )
    merged_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when the PR was merged"
    )

    head_ref: Optional[str] = Field(
        default=None, description="Name of the source branch (head)"
    )
    head_sha: Optional[str] = Field(
        default=None, description="Current HEAD SHA of the source branch"
    )
    base_ref: Optional[str] = Field(
        default=None, description="Name of the target branch (base)"
    )

    user_login: Optional[str] = Field(
        default=None, description="Username of the PR author"
    )
    draft: Optional[bool] = Field(
        default=None, description="Indicates if the PR is a draft"
    )
    merge_commit_sha: Optional[str] = Field(
        default=None, description="SHA of the merge commit, if merged"
    )


# class PRList(BaseModel):
#     pull_requests: List[PR]


# Pull-request review ----------------------------------------------------------
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


# Commit belonging to a pull-request -------------------------------------------
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
