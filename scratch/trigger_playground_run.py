import json
import urllib.request
import uuid

url = "http://127.0.0.1:8080/run"
headers = {"Content-Type": "application/json"}

# Generate a new session ID for the playground run
session_id = str(uuid.uuid4())

# Send a mock high-risk billing PR payload to test the workflow
payload = {
    "app_name": "pr_triage_agent",
    "user_id": "user",
    "session_id": session_id,
    "new_message": {
        "role": "user",
        "parts": [
            {
                "text": json.dumps(
                    {
                        "repository": "acme/web-app",
                        "pull_request": {
                            "number": 42,
                            "title": "Refactor authentication and billing middleware",
                            "author": "alice",
                            "base_branch": "main",
                            "head_branch": "feature/auth-refactor",
                        },
                    }
                )
            }
        ],
    },
}

req = urllib.request.Request(
    url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
)

try:
    with urllib.request.urlopen(req) as response:
        res_data = response.read().decode("utf-8")
        print("\n\033[92mSuccess! Triggered run on playground server.\033[0m")
        print(f"Session ID: {session_id}")
        print("Check your browser at http://127.0.0.1:8080 to interact with the run!\n")
except Exception as e:
    print(f"\033[91mError triggering playground run: {e}\033[0m")
