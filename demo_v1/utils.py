import logging


def filter_searches(results: dict | list[dict]) -> list[dict]:
    """
    Removes duplicate search results from Tavily API response(s).
    """
    # Single Tavily search results --> dict['results']
    if isinstance(results, dict):
        sources = results["results"]

    # Multiple Tavily searches --> list(dict['results'])
    elif isinstance(results, list):
        sources = []

        for res in results:
            if isinstance(res, dict) and "results" in res:
                sources.extend(res["results"])
            else:
                sources.extend(res)
    else:
        raise ValueError(
            "Input must be either a dict with 'results' or a list of search results"
        )

    # Filter duplicates by source URL
    unique_urls = set()
    unique_sources = []
    for source in sources:
        if source["url"] not in unique_urls:
            unique_urls.add(source["url"])
            unique_sources.append(source)

    return unique_sources


def format_results(sources: list[dict], max_tokens: int = 1000) -> str:
    """
    Formats a results from Tavily or the local database while limiting the context length by max_tokens.
    """
    formatted_text = "Sources:\n\n"
    for source in sources:
        formatted_text += f"Source {source['title']}:\n===\n"
        formatted_text += f"URL: {source['url']}\n===\n"
        formatted_text += (
            f"Most relevant content from source: {source['content']}\n===\n"
        )

        # Tavily provides the raw content and the summarized content
        raw_content = source.get("raw_content", "")

        # Log warning only on Tavily results
        if (source["content"]) and (source["raw_content"] is None):
            raw_content = ""
            logging.warning(f"No raw_content found for source {source['url']}")

        # 1 token ~ 4 characters
        char_limit = max_tokens * 4

        if len(raw_content) > char_limit:
            raw_content = raw_content[:char_limit] + "... [truncated]"
        formatted_text += (
            f"Full source content limited to {max_tokens} tokens: {raw_content}\n\n"
        )

    return formatted_text.strip()
