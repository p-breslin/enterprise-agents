from pydantic import BaseModel, Field
from typing import Optional, List, Union


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
    key: str
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
