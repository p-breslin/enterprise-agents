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


# Identifies a specific branch within a repo -----------------------------------
class Branch(BaseModel):
    owner: str = Field(description="Repository owner (user or org)")
    repo: str = Field(description="Repository name")
    branch_name: str = Field(
        description="Name of the discovered branch matching the criteria"
    )


class BranchList(BaseModel):
    target_branches: List[Branch] = Field(
        description="List of branches matching the specified criteria across the input repositories"
    )


# Pull-request numbers ---------------------------------------------------------
class PRNumbers(BaseModel):
    owner: str = Field(description="Repository owner (user or org)")
    repo: str = Field(description="Repository name")
    relevant_pr_numbers: List[int] = Field(
        description="List of PR numbers updated since the specified cutoff time"
    )


# Pull-request Enrichment ======================================================


# Simplified info for a single PR review ---------------------------------------
class ReviewDetail(BaseModel):
    reviewer_login: Optional[str] = Field(
        default=None, description="Username of the reviewer"
    )
    state: Optional[str] = Field(
        default=None,
        description="Review state (e.g., 'APPROVED', 'CHANGES_REQUESTED', 'COMMENTED')",
    )
    submitted_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when the review was submitted"
    )


# Simplified info for a file change in a PR ------------------------------------
class FileChangeDetail(BaseModel):
    filename: Optional[str] = Field(
        default=None, description="Path of the changed file"
    )
    status: Optional[str] = Field(
        default=None,
        description="Status of the file (e.g., 'added', 'modified', 'removed')",
    )
    additions: Optional[int] = Field(default=None, description="Number of lines added")
    deletions: Optional[int] = Field(
        default=None, description="Number of lines deleted"
    )


# Simplified info of an individual status check/commit status ------------------
class StatusCheckDetail(BaseModel):
    id: Optional[int] = Field(
        default=None, description="The unique ID of the status check"
    )
    context: Optional[str] = Field(
        default=None, description="The name/context of the status check"
    )
    state: Optional[str] = Field(
        default=None,
        description="State of the check (e.g., 'success', 'failure', 'pending', 'error')",
    )
    target_url: Optional[str] = Field(
        default=None, description="URL link to the details of the check"
    )
    description: Optional[str] = Field(
        default=None, description="A short description of the status"
    )


# Comprehensive details for a single PR ----------------------------------------
class PRDetails(BaseModel):
    # --- Identifiers ---
    owner: str = Field(description="Repository owner (user or org)")
    repo: str = Field(description="Repository name")
    pr_number: int = Field(description="Pull request number within the repository")

    # --- Core PR Details (from get_pull_request) ---
    title: Optional[str] = Field(default=None, description="Title of the pull request")
    body: Optional[str] = Field(
        default=None, description="Body/description of the pull request"
    )
    state: Optional[str] = Field(
        default=None,
        description="State of the pull request (e.g., 'open', 'closed', 'merged')",
    )
    author_login: Optional[str] = Field(
        default=None, description="Username of the PR author (from user.login)"
    )
    created_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when the PR was created"
    )
    updated_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when the PR was last updated"
    )
    closed_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when the PR was closed"
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

    # --- Status Check Details (from get_pull_request_status) ---
    status_check_state: Optional[str] = Field(
        default=None,
        description="Overall combined status state for the head commit (e.g., 'success', 'failure', 'pending')",
    )
    status_checks: List[StatusCheckDetail] = Field(
        default_factory=list,
        description="List of individual status checks run on the head commit",
    )

    # --- Review Details (from get_pull_request_reviews) ---
    reviews: List[ReviewDetail] = Field(
        default_factory=list,
        description="List of reviews submitted for the pull request",
    )

    # --- File Change Details (from get_pull_request_files) ---
    files_changed: List[FileChangeDetail] = Field(
        default_factory=list, description="List of files changed in the pull request"
    )


# ==============================================================================


# Details of a single commit associated with a specific PR ---------------------
class PRCommits(BaseModel):
    owner: str = Field(description="Repository owner (user or org) from input context")
    repo: str = Field(description="Repository name from input context")
    pr_number: int = Field(description="Pull request number from input context")
    sha: str = Field(description="The 40-character commit SHA")
    message: str = Field(description="The commit message")
    author_login: Optional[str] = Field(
        default=None,
        description="Username login of the commit author (if available, otherwise may be derived from author name)",
    )
    committed_date: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when the commit was committed"
    )


class CommitList(BaseModel):
    commits: List[PRCommits] = Field(
        description="List of commit details associated with the specified PR(s)"
    )
