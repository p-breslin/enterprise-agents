import json
import asyncio
import logging
from scripts.orchestrator import run_research_pipeline


def main():
    logging.basicConfig(level=logging.INFO)

    company_name = "Tesla"
    final_output = asyncio.run(run_research_pipeline(company_name))

    print("\n=== Final Structured Output ===")
    if final_output:
        print(json.dumps(final_output, indent=2))
    else:
        print("No final output was produced.")


if __name__ == "__main__":
    main()
    # PYTHONPATH=$(pwd) python3 tests/test.py
