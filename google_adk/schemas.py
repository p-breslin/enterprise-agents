from typing import Optional, List
from pydantic import BaseModel, Field


class JiraIssues(BaseModel):
    issue_type: str = Field(description="The type of issue, e.g., Bug, Task, Epic.")
    issue_id: str = Field(description="The unique key of the issue, e.g., QA-123.")
    summary: str = Field(description="Short description of the issue.")
    assignee: Optional[str] = Field(description="Name of the assigned user.")
    reporter: Optional[str] = Field(
        description="Name of the user who created the issue."
    )
    priority: Optional[str] = Field(description="Priority label, e.g., High, Medium.")
    status: str = Field(description="Current workflow status of the issue.")
    resolution: Optional[str] = Field(
        description="Resolution label, e.g., Done, Won't Fix."
    )
    created: str = Field(description="Date the issue was created (ISO 8601).")
    updated: str = Field(description="Date the issue was last updated (ISO 8601).")
    due_date: Optional[str] = Field(description="Due date, if applicable (ISO 8601).")
    end_date: Optional[str] = Field(
        description="Resolution or closure date (ISO 8601)."
    )
    description: Optional[str] = Field(description="Detailed issue description.")


class JiraIssuesList(BaseModel):
    issues: List[JiraIssues]
