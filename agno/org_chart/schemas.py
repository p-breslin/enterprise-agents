from pydantic import BaseModel, Field
from typing import Optional, List


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
    story_key: str  # Match name used in prompt output
    summary: str
    status: str
    assignee: Optional[str]
    epic_key: str  # Explicitly add based on prompt instructions
    created: str  # ISO 8601
    updated: Optional[str] = None
    resolved: Optional[str] = None
    priority: Optional[str] = None
    project: Optional[str] = None
    reporter: Optional[str] = None
    story_points: Optional[float] = None


class IssueList(BaseModel):
    issues: List[Issue]
