from teams.org_structure import create_team


def main():
    """
    Purpose:
        Runs the OrgStructureTeam agent pipeline to generate a project/team structure from recent Jira data.

    Behavior:
        - Instantiates the OrgStructureTeam
        - Executes the multi-agent flow (fetch → analyze → estimate)
        - Prints the final structured org map with seniority labels
    """
    print("Initializing OrgStructureTeam...")
    team = create_team()

    print("\nRunning agentic flow...\n")
    # result = team.run("Build an org structure from recent Jira tickets.")
    team.print_response(
        "Generate the full team/project structure from recent Jira data and label engineer seniority.",
        stream=True,
    )

    # print("\nFinal structured output:\n")
    # print(result)

    # print("\nAgent memory trace:")
    # for msg in team.memory.messages:
    #     print(f"{msg['role'].upper()}: {msg['content'][:200]}")


if __name__ == "__main__":
    main()
