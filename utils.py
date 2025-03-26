import json


def is_valid_json(response, json_check=False):
    """
    Check if the response is valid JSON.
    """
    try:
        json.loads(response)
        json_check = True
        return json_check
    except json.JSONDecodeError:
        return json_check
