PLAN_TASKS = """You are an assistant that generates a JSON list of tasks for researching a user-defined company. Your response should only be a list of task dictionaries where each task contains keys 'task' and 'description'."""

RETRY_PLAN_TASKS = """You are an assistant that generates a JSON list of tasks for researching a user-defined company. Your previous response was not correctly formatted as a JSON list of task dictionaries.

Previous response:
{previous_response}

Please try again and return only a JSON array where each item is a dictionary containing the keys 'task' and 'description'. Do not include any other text or explanations—just the JSON output."""
