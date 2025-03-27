import re
import json
import asyncio
import logging

from openai import OpenAI
from tavily import AsyncTavilyClient
from app.main.embedding_search import EmbeddingSearch
from features.multi_agent.LLM import call_llm
from features.multi_agent.utility import filter_searches, format_results
from features.multi_agent.config import Configuration
from features.multi_agent.state import OverallState
from features.multi_agent.prompts import (
    QUERY_LIST_PROMPT,
    QUERY_GENERATOR_PROMPT,
    RESEARCH_PROMPT,
    EXTRACTION_PROMPT,
)


logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
cfg = Configuration()
tavily_async_client = AsyncTavilyClient(cfg.TAVILY_API_KEY)
chatgpt_client = OpenAI(api_key=cfg.OPENAI_API_KEY)


async def run_research_pipeline(company: str) -> OverallState:
    """
    Orchestrates the multi-agent workflow for researching a company.
    1) Check if data is already in the DB (Step 1).
    2) Generate search queries if needed (Step 2).
    3) Use Tavily to get new data (Step 3).
    4) Compile research notes (Step 4).
    5) Extract structured JSON (Step 5).
    """
    # Initialize shared state
    state = OverallState(company=company)

    # Step 1: Check database for relevant data
    db_check = await agent_check_database(state)
    if db_check:
        logging.info("Relevant information in database; compiling research.")
        await agent_compile_research(state)  # Compile research from stored data
    else:
        # Step 2: Generate queries
        agent_generate_queries(state)

        # Step 3: Tavily web search
        await agent_web_search(state)

        # Step 4: Compile research from search data
        await agent_compile_research(state)

    # Step 5: Extract structured JSON from the compiled research
    agent_extract_schema(state)

    # state.final_output should have the final JSON output
    return state


async def agent_check_database(state: OverallState) -> bool:
    """
    Step 1: Checks if relevant data exists in database. If so, stores in state.search_results.
    """
    vector_search = EmbeddingSearch(state.company)
    metadata, docs = vector_search.run()

    if not metadata:
        logging.info("No stored data; initiating web search.")
        return False

    # Store data for later user
    logging.info("Using existing data from DB.")
    state.search_results = [
        {
            "url": metadata["link"],
            "title": metadata["title"],
            "content": docs,
            "raw_content": None,
        }
    ]
    return True


def agent_generate_queries(state: OverallState) -> None:
    """
    Step 2: Generates relevant search queries based on the company's name and schema. Stores the resulting list of queries in state.search_queries.
    """
    instructions = QUERY_GENERATOR_PROMPT.format(
        company=state.company,
        schema=json.dumps(state.output_schema, indent=2),
        N_searches=cfg.N_searches,
    )
    messages = [
        {"role": "system", "content": instructions},
        {
            "role": "user",
            "content": QUERY_LIST_PROMPT.format(N_searches=cfg.N_searches),
        },
    ]
    output = call_llm(cfg.OPENAI_API_KEY, messages)
    search_queries = re.findall(r'"\s*(.*?)\s*"', output)  # remove enumeration
    state.search_queries = search_queries
    logging.info(f"Generated search queries: {state.search_queries}")


async def agent_web_search(state: OverallState) -> None:
    """
    Step 3: Uses Tavily with the generated queries to retrieve new information. The results are stored as a list of dicts in state.search_results.
    """
    if not state.search_queries:
        logging.warning("No search queries were found; regenerating queries.")
        agent_generate_queries(state)

    tasks = []
    for query in state.search_queries:
        tasks.append(tavily_async_client.search(query, **cfg.TAVILY_SEARCH_PARAMS))

    # Execute all searches concurrently
    search_results = await asyncio.gather(*tasks)

    # Filter search results for duplocates and store them
    unique_results = filter_searches(search_results)
    state.search_results = unique_results


async def agent_compile_research(state: OverallState) -> None:
    """
    Step 4: Compiles research notes from the data in state.search_results. The compiled notes are appended to state.research.
    """
    # Format the found results into a context string
    context_str = format_results(state.search_results)

    instructions = RESEARCH_PROMPT.format(
        company=state.company,
        schema=state.output_schema,
        context=context_str,
    )
    research_notes = call_llm(
        cfg.OPENAI_API_KEY, messages=[{"role": "user", "content": instructions}]
    )
    state.research.append(research_notes)
    logging.info("Compiled research notes added to state.research.")


def agent_extract_schema(state: OverallState) -> None:
    """
    Step 5: Takes the compiled research (state.research) and prompts the LLM
    to output JSON that strictly matches the schema in state.output_schema.
    The parsed JSON is saved in state.final_output.
    """
    if not state.research:
        logging.warning("No research notes available to extract schema from.")
        return

    instructions = EXTRACTION_PROMPT.format(
        schema=state.output_schema,
        research=state.research,
    )
    output = call_llm(
        cfg.OPENAI_API_KEY,
        messages=[{"role": "user", "content": instructions}],
        schema=state.output_schema,
    )

    try:
        # Validate output
        data = json.loads(output)
        state.final_output = data
        logging.info("Final output successfully parsed as JSON.")

    except json.JSONDecodeError:
        logging.error("Failed to parse JSON from LLM response.")
        logging.error(f"LLM response was: {output}")
        state.final_output = {}


def agent_store_data():
    """Agent 7: Stores new data"""
    pass


def agent_return_results():
    """Agent 8: Returns results"""
    pass
