import logging
from scripts.secrets import Secrets
from typing import List, Union, Optional, Dict, Any


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


def get_prompt(cfg: dict, system_id=None, template_id=None):
    """
    Prompt retrieval from predefined prompts in configs.
    """
    system_prompt = None
    if system_id:
        system_prompt = cfg["system_prompts"][system_id]["prompt_text"]

    template = None
    if template_id:
        template = cfg["prompt_templates"][template_id]["template_text"]

    return system_prompt, template


def get_api_key(service: str) -> str:
    """
    Fetches an API key from the environment using the convention: {SERVICE}_API_KEY.
    """
    api_keys = Secrets()
    env_key = f"{service.upper()}_API_KEY"
    key = getattr(api_keys, env_key)

    if not key:
        raise ValueError(f"Missing environment variable: {env_key}")
    return key


def agent_color_code(agent_name):
    """
    Defines a HTML color for the agent / process in the UI display.
    """
    AGENT_COLORS = {
        "Orchestrator": "#55e5e3",
        "GraphQueryAgent": "#879557",
        "QueryGenerationAgent": "#c57f00",
        "WebSearchAgent": "#8e44ad",
        "ResearchAgent": "#d35400",
        "ExtractionAgent": "#0066cc",
        "GraphUpdateAgent": "#e5559d",
    }
    color = AGENT_COLORS.get(agent_name, "#333")
    return f'<span style="color:{color}; font-weight:600;">{agent_name}</span>'


def format_agent_message(update, logs=False):
    """
    Formats the agent messages as nice HTML for the UI display.
    """
    update_type = update.get("type", "unknown")
    agent_name = update.get("agent_name", "")
    message = update.get("message", "")
    event_type = update.get("event_type", "")
    status = update.get("status", "")

    agent_html = agent_color_code(agent_name)

    # EVENT
    if update_type == "event":
        # horizontal line above event
        return (
            "<hr style='border: none; border-top: 1px dashed #ccc; margin-top: 1.5em;' />"
            f"<div><strong>{message}</strong> <code>{event_type}</code></div>"
        )

    # DISPATCH
    elif update_type == "dispatch":
        return f"<div style='margin-left: 1em;'><em>Dispatching</em>  <code>{event_type}</code> to {agent_html}...</div>"

    # ACTION
    elif update_type == "agent_action":
        return f"<div style='margin-left: 1em;'>{agent_html}: {message}</div>"

    # LOG
    elif update_type == "agent_log":
        if logs:
            return f"<div style='margin-left: 1em;'><em>{agent_html} Log:</em> {message}</div>"
        else:
            return None

    # WARNING
    elif update_type == "warning":
        return f'<div style="color:orange;"><strong>Warning:</strong> {message}</div>'

    # ERROR
    elif update_type == "error":
        return f'<div style="color:red;"><strong>ERROR:</strong> {message}</div>'

    # COMPLETION
    elif update_type == "pipeline_end":
        if status == "success":
            return f'<div style="color:green;"><strong>Workflow Success:</strong> {update.get("message", "")}</div>'
        else:
            return f'<div style="color:red;"><strong>Workflow Failed:</strong> {update.get("message", "")}</div>'

    # Fallback
    if message or event_type:
        return f"<div>{message or event_type}</div>"


def normalize_unique_items(
    input_list: List[Any], key: Optional[str] = None, case_insensitive: bool = True
) -> List[Union[str, Dict]]:
    """
    Purpose:
        Deduplicates a list of strings or a list of dicts (by key) in a normalized way.

    Params:
        input_list: List of strings or dicts.
        key: Deduplicatse based on dict[key], otherwise assumes List[str].
        case_insensitive: Normalize by lowercasing if True.

    Returns:
        List[str] or List[Dict]: The deduplicated and cleaned list, preserving order.
    """
    seen = set()
    result = []

    for item in input_list:
        # String mode
        if key is None:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            norm = cleaned.lower() if case_insensitive else cleaned
            if cleaned and norm not in seen:
                seen.add(norm)
                result.append(cleaned)

        # Dict mode
        else:
            if not isinstance(item, dict):
                continue
            value = item.get(key)
            if not isinstance(value, str):
                continue
            cleaned = value.strip()
            norm = cleaned.lower() if case_insensitive else cleaned
            if cleaned and norm not in seen:
                seen.add(norm)
                result.append(item)

    return result
