import requests

url = "http://localhost:7868/api/v1/run/my_jira_mcp"
payload = {
    "input_value": "Get any JIRA project issues for project key CAP",
    "output_type": "chat",
    "input_type": "chat",
}
headers = {"Content-Type": "application/json"}

try:
    # Send API request
    response = requests.request("POST", url, json=payload, headers=headers)
    response.raise_for_status()

    # Print response
    print(response.text)

except requests.exceptions.RequestException as e:
    print(f"Error making API request: {e}")
except ValueError as e:
    print(f"Error parsing response: {e}")
