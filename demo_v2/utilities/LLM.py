import ollama
import logging
from openai import OpenAI
from typing import List, Dict

logger = logging.getLogger(__name__)


def call_local_llm(messages):
    """
    Sends a list of messages (role + content) to the local LLM and returns its response as a string. Wraps Ollama's API call.
    """
    try:
        response = ollama.chat(
            model="granite3.2:2b-instruct-q4_K_M",
            messages=messages,
            stream=False,
            options={"keep_alive": "5m"},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        logging.error(f"LLM request failed: {e}")
        return f"LLM Error: {str(e)}"


def call_llm(
    api_key: str,
    messages: List[Dict[str, str]],
    model: str = "gpt-4o-mini-2024-07-18",
    json_mode: bool = False,
) -> str:
    """
    Sends a list of messages (role + content) to an OpenAI LLM.

    Args:
        api_key: The OpenAI API key.
        messages: A list of message dictionaries (e.g., [{"role": "user", "content": "..."}]).
        model: The OpenAI model to use.
        json_mode: If True, requests JSON output format from the API.

    Returns:
        The content of the LLM's response as a string.
    """
    client = OpenAI(api_key=api_key)
    response_format_param = None
    if json_mode:
        logger.debug("Requesting JSON mode from OpenAI API.")
        response_format_param = {"type": "json_object"}

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=response_format_param,
        )
        content = response.choices[0].message.content

        if json_mode:
            logger.debug(
                f"OpenAI structured response received (length: {len(content)})."
            )
        else:
            logger.debug(
                f"OpenAI unstructured response received (length: {len(content)})."
            )

        logger.debug(f"Token usage: {response.usage.total_tokens}")
        return content.strip()

    except Exception as e:
        logger.error(f"ChatGPT request failed: {e}")
        return f"ChatGPT Error: {str(e)}"
