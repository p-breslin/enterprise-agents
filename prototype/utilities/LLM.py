import ollama
import logging
from typing import List, Dict
from utilities.helpers import get_api_key

from openai import OpenAI
from google import genai
from google.genai import types


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
    messages: List[Dict[str, str]],
    provider: str = "OPENAI",
    model: str = None,
    json_mode: bool = False,
) -> str:
    """
    Sends a list of messages (role + content) to an LLM provider (OpenAI or Google). Returns the content of the LLM's response as a string.
    """
    api_key = get_api_key(service=provider.upper())

    if provider.lower() == "openai":
        model = model or "gpt-4o-mini-2024-07-18"
        client = OpenAI(api_key=api_key)

        response_format_param = {"type": "json_object"} if json_mode else None

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format=response_format_param,
            )
            content = response.choices[0].message.content
            logger.debug(
                f"OpenAI response received (tokens used: {response.usage.total_tokens})"
            )
            return content.strip()
        except Exception as e:
            logger.error(f"OpenAI request failed: {e}")
            return f"OpenAI Error: {str(e)}"

    elif provider.lower() == "gemini":
        model = model or "gemini-2.0-flash"
        client = genai.Client(api_key=api_key)

        system_instruction = None
        contents = []
        for m in messages:
            if m["role"] == "system":
                system_instruction = m["content"]
            else:
                contents.append(
                    types.Content(role=m["role"], parts=[types.Part(text=m["content"])])
                )

        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction
        if json_mode:
            config.response_mime_type = "application/json"

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return response.candidates[0].content.parts[0].text.strip()
        except Exception as e:
            logger.error(f"Gemini request failed: {e}")
            return f"Google Gemini Error: {str(e)}"

    else:
        raise ValueError("Invalid provider specified. Must be 'openai' or 'google'.")
