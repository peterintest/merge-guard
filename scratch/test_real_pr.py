#!/usr/bin/env python3
# ruff: noqa: E402
import argparse
import asyncio
import os
import sys

# Load .env manually if present
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from merge_guard.agent import root_agent


async def run_real_pr(repository: str, pr_number: int):
    # 1. Check GITHUB_TOKEN
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        print(
            "\n\033[91mError: GITHUB_TOKEN or GITHUB_PERSONAL_ACCESS_TOKEN is not set.\033[0m"
        )
        print("Please set it in your environment or in the .env file:")
        print('  export GITHUB_TOKEN="your_token"\n')
        sys.exit(1)

    print(f"\n\033[96mInitializing Triage Agent for:\033[0m {repository} # {pr_number}")
    print("\033[90mConnecting to GitHub MCP server to fetch real PR data...\033[0m\n")

    # 2. Build mock Pub/Sub push notification payload
    payload = {"repository": repository, "pull_request": {"number": pr_number}}

    # Construct types.Content matching Pub/Sub Push format
    import base64
    import json

    envelope = {
        "subscription": "projects/my-gcp-project/subscriptions/ambient-pr-triage-sub",
        "message": {
            "messageId": "msg-real-pr",
            "data": base64.b64encode(json.dumps(payload).encode("utf-8")).decode(
                "utf-8"
            ),
        },
    }

    user_message = types.Content(
        role="user", parts=[types.Part.from_text(text=json.dumps(envelope))]
    )

    import uuid

    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name="ambient_pr_triage_agent",
    )
    session = await session_service.create_session(
        app_name="ambient_pr_triage_agent",
        user_id="cli_tester",
        session_id=str(uuid.uuid4()),
    )

    # 3. Execute runner loop
    paused = False
    interrupt_id = None

    async for event in runner.run_async(
        new_message=user_message, user_id="cli_tester", session_id=session.id
    ):
        if hasattr(event, "interrupt_id"):
            paused = True
            interrupt_id = event.interrupt_id
            print(f"\n\033[93m[Manual Review Pause: {interrupt_id}]\033[0m")
            print(event.message)
            print("-" * 60)
        else:
            # Print general triage updates
            author = getattr(event, "author", "System")
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"\033[94m[{author}]:\033[0m {part.text}")

    # 4. Handle Human-in-the-Loop decision input if paused
    if paused:
        print("\n\033[1mPlease enter your review decision:\033[0m")
        decision = input("Decision (Approve / Request Changes): ").strip()
        comments = input("Comments: ").strip()

        resume_payload = {"decision": decision, "comments": comments}

        print("\n\033[90mResuming agent run with decision...\033[0m\n")

        async for event in runner.resume_async(
            session_id=session.id, interrupt_id=interrupt_id, payload=resume_payload
        ):
            author = getattr(event, "author", "System")
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"\033[94m[{author}]:\033[0m {part.text}")

    print("\n\033[92mTriage execution completed successfully.\033[0m\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test Ambient PR Triage Agent with a live GitHub PR"
    )
    parser.add_argument(
        "-r", "--repo", default="google/adk", help="Repository path (owner/repo)"
    )
    parser.add_argument("-p", "--pr", type=int, default=1, help="Pull request number")
    args = parser.parse_args()

    asyncio.run(run_real_pr(args.repo, args.pr))
