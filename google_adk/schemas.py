from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class Epic(BaseModel):
    epic_key: str = Field(description="Unique key of the epic")
    summary: str = Field(description="Title or summary of the epic")
    project: str = Field(description="The project this epic belongs to")


class Story(BaseModel):
    story_key: str = Field(description="Unique key of the story")
    summary: str = Field(description="Title of the story")
    status: str = Field(description="Current Jira status")
    assignee: str = Field(description="Assignee name or ID")
    epic_key: str = Field(description="Key of the parent epic")


class IssueDetail(BaseModel):
    issue_key: str
    issue_type: str
    summary: str
    status: str
    assignee: Optional[str]
    reporter: Optional[str]
    created: str  # ISO 8601
    updated: str  # ISO 8601
    epic_key: Optional[str]  # if available from fields
    story_points: Optional[float]
    project: Optional[str]


class UserIssues(BaseModel):
    assignee: str
    issues: List[IssueDetail]


class UserWorkload(BaseModel):
    user: str
    total_issues: int
    active_issues: int
    story_points: Optional[float]
    epics: List[str]
    status_summary: Dict[str, int]


class TeamMember(BaseModel):
    name: str
    role: Optional[str] = None
    issues_assigned: int
    active_issues: int
    story_points: Optional[float]
    epics: List[str]
    status_summary: Dict[str, int]


class Team(BaseModel):
    team_name: str
    epics: List[str]
    projects: List[str]
    members: List[TeamMember]
    manager: Optional[str]


class OrgStructure(BaseModel):
    teams: List[Team]
    unassigned_issues: Optional[List[IssueDetail]] = None
    users_without_issues: Optional[List[dict]] = None  # name, last_active_issue
