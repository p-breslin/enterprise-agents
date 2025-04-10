import os
import json
import yaml
import asyncio
from typing import List
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel
from mcp import StdioServerParameters

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from agno.models.openai import OpenAIChat

import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)

load_dotenv()
JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")


class JiraIssue(BaseModel):
    issue_id: str
    summary: str
    assignee: str
    project: str
    last_updated: str


def load_prompt(prompt_key: str) -> str:
    path = Path(__file__).parent / "prompts.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)[prompt_key]


def extract_json(content: str) -> str:
    if content.startswith("```json"):
        return content.strip("` \n")[6:].strip()
    return content.strip()


def main():
    asyncio.run(
        run_agent(
            "List issues updated in the last 30 days and show who is working on them."
        )
    )


async def run_agent(message: str) -> List[JiraIssue]:
    server_params = StdioServerParameters(
        command="mcp-atlassian",
        args=[
            f"--jira-url={JIRA_SERVER_URL}",
            f"--jira-username={JIRA_USERNAME}",
            f"--jira-token={JIRA_TOKEN}",
        ],
    )

    async with MCPTools(
        server_params=server_params,
        include_tools=[
            "jira_get_issue",
            "jira_search",
            "jira_get_project_issues",
            "jira_get_epic_issues",
            "jira_get_transitions",
            "jira_get_agile_boards",
            "jira_get_board_issues",
            "jira_get_sprints_from_board",
            "jira_get_sprint_issues",
        ],
    ) as mcp_tools:
        agent = Agent(
            model=OpenAIChat(id="gpt-4o-mini"),
            tools=[mcp_tools],
            instructions=load_prompt("jira_agent"),
            markdown=True,
            show_tool_calls=True,
        )

        response = agent.run(message)
        try:
            raw_json = extract_json(response.content)
            structured = json.loads(raw_json)
            issues = [JiraIssue(**item) for item in structured]
            print("Parsed structured issues:\n")
            for issue in issues:
                print(issue.json(indent=2))
            return issues
        except Exception as e:
            print("Failed to parse structured output:", e)
            print("Raw response:\n", response.content)
            return []


if __name__ == "__main__":
    main()


# def main():
#     agent = Agent(
#         name="JiraFetcherAgent",
#         model=Gemini(id="gemini-2.0-flash-exp"),
#         tools=[JiraTools()],
#         description="Jira Agent",
#         instructions=load_prompt("jira_agent"),
#         structured_outputs=True,
#         show_tool_calls=True,
#         markdown=False,
#     )
#     resp = agent.run(
#         message="List issues updated in the last 30 days and who is working on them."
#     )
#     print(resp.content)


# if __name__ == "__main__":
#     main()
