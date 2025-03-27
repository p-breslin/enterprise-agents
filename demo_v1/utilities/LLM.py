import ollama
import logging
from openai import OpenAI


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


def call_llm(api_key, messages, schema=False):
    """
    Sends a list of messages (role + content) to ChatGPT.
    """
    client = OpenAI(api_key=api_key)
    try:
        if schema:
            response = client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",
                messages=messages,
                response_format=schema,
            )
            content = response.choices[0].message.content
            logging.debug(f"ChatGPT structured response: {content}")
            logging.debug(f"Token usage: {response.usage.total_tokens}")
            return content
        else:
            response = client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18", messages=messages
            )
            content = response.choices[0].message.content
            logging.debug(f"ChatGPT unstructured response: {content}")
            logging.debug(f"Token usage: {response.usage.total_tokens}")
            return content

    except Exception as e:
        logging.error(f"ChatGPT request failed: {e}")
        return f"ChatGPT Error: {str(e)}"
