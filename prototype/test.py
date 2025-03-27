import json
import asyncio
import logging
from features.multi_agent.factory import run_research_pipeline


def main():
    logging.basicConfig(level=logging.INFO)

    company_name = "Tesla"
    state = asyncio.run(run_research_pipeline(company_name))

    print("\n=== Final Structured Output ===")
    if state.final_output:
        print(json.dumps(state.final_output, indent=2))
    else:
        print("No final output was produced.")


if __name__ == "__main__":
    main()
