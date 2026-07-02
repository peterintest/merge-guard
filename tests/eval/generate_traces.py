# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import json
import os
import sys
import uuid
from typing import Any

# Apply nest_asyncio to allow nesting loops
# import nest_asyncio
# nest_asyncio.apply()

# Set python path to allow importing merge_guard
sys.path.insert(
    0, os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from merge_guard.agent import root_agent


def content_to_dict(content: Any) -> dict:
    """Translates ADK/GenAI Content objects into standard dictionary representation."""
    if not content:
        return {}
    parts = []
    for part in content.parts:
        if part.text:
            parts.append({"text": part.text})
        elif part.function_call:
            parts.append(
                {
                    "function_call": {
                        "name": part.function_call.name,
                        "args": part.function_call.args,
                    }
                }
            )
        elif part.function_response:
            parts.append(
                {
                    "function_response": {
                        "name": part.function_response.name,
                        "response": part.function_response.response,
                    }
                }
            )
    return {"role": content.role or "model", "parts": parts}


def event_to_dict(author: str, content_dict: dict) -> dict:
    """Helper to wrap events."""
    return {"author": author, "content": content_dict}


async def generate_traces():
    dataset_path = "tests/eval/datasets/basic-dataset.json"
    output_path = "artifacts/traces/generated_traces.json"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(dataset_path) as f:
        dataset = json.load(f)

    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent, session_service=session_service, app_name="merge_guard"
    )

    output_cases = []

    for case in dataset["eval_cases"]:
        case_id = case["eval_case_id"]
        print(f"Running scenario: {case_id}")

        prompt_text = case["prompt"]["parts"][0]["text"]
        user_message = types.Content(
            role="user", parts=[types.Part.from_text(text=prompt_text)]
        )

        session = await session_service.create_session(
            app_name="merge_guard", user_id="eval_user", session_id=str(uuid.uuid4())
        )

        turns = []
        current_events = []

        # Add initial user prompt event
        current_events.append(
            event_to_dict("user", {"role": "user", "parts": [{"text": prompt_text}]})
        )

        # Run first turn
        paused = False
        interrupt_id = None

        async for event in runner.run_async(
            new_message=user_message, user_id="eval_user", session_id=session.id
        ):
            # Check if this is a RequestInput
            if hasattr(event, "interrupt_id"):
                paused = True
                interrupt_id = event.interrupt_id
                # Record it as a request_input function call event
                req_content = {
                    "role": "model",
                    "parts": [
                        {
                            "function_call": {
                                "name": "adk_request_input",
                                "args": {
                                    "interruptId": event.interrupt_id,
                                    "message": event.message,
                                },
                            }
                        }
                    ],
                }
                current_events.append(
                    event_to_dict("ambient_pr_triage_agent", req_content)
                )
            else:
                author = getattr(event, "author", "ambient_pr_triage_agent")
                content_dict = content_to_dict(event.content)
                if (
                    (not content_dict or not content_dict.get("parts"))
                    and hasattr(event, "output")
                    and event.output is not None
                ):
                    # Serialize structured output (like TriageDecisionOutput) to text parts in trace logs
                    out_val = event.output
                    if hasattr(out_val, "model_dump"):
                        out_dict = out_val.model_dump()
                    elif isinstance(out_val, dict):
                        out_dict = out_val
                    else:
                        out_dict = str(out_val)
                    content_dict = {
                        "role": "model",
                        "parts": [
                            {"text": f"System Triage Decision: {json.dumps(out_dict)}"}
                        ],
                    }
                current_events.append(event_to_dict(author, content_dict))

        turns.append({"turn_index": 0, "events": current_events})

        if paused:
            # Handle HITL resume decision using ReviewDecisionInput schema: {"decision": ..., "comments": ...}
            decision = "Approve"
            comments = "Approved by human reviewer after LLM risk analysis."

            if "injection" in case_id:
                decision = "Request Changes"
                comments = "Rejected: Blocked due to prompt injection attempt."
            elif "gaps" in case_id:
                decision = "Request Changes"
                comments = (
                    "Request Changes: Insufficient testing coverage on billing updates."
                )

            resume_response = {"decision": decision, "comments": comments}

            resume_message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name="adk_request_input",
                            id=interrupt_id,
                            response=resume_response,
                        )
                    )
                ],
            )

            resume_events = []
            # Add user resume action event
            user_resume_event = {
                "author": "user",
                "content": {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": "adk_request_input",
                                "response": resume_response,
                            }
                        }
                    ],
                },
            }
            resume_events.append(user_resume_event)

            async for event in runner.run_async(
                new_message=resume_message, user_id="eval_user", session_id=session.id
            ):
                author = getattr(event, "author", "ambient_pr_triage_agent")
                content_dict = content_to_dict(event.content)
                resume_events.append(event_to_dict(author, content_dict))

            turns.append({"turn_index": 1, "events": resume_events})

        # Find the last model/workflow response
        last_response = None
        for turn in reversed(turns):
            for event in reversed(list(turn["events"])):
                if (
                    event["author"] == "ambient_pr_triage_agent"
                    and event["content"].get("role") == "model"
                ):
                    parts = event["content"].get("parts", [])
                    if parts and (
                        any("text" in p for p in parts)
                        or any("function_call" in p for p in parts)
                    ):
                        last_response = event["content"]
                        break
            if last_response:
                break

        if not last_response:
            last_response = turns[-1]["events"][-1]["content"]

        # Compile case trace data
        case_trace = {
            "eval_case_id": case_id,
            "agent_data": {
                "agents": {
                    "ambient_pr_triage_agent": {
                        "agent_id": "ambient_pr_triage_agent",
                        "instruction": root_agent.description,
                    }
                },
                "turns": turns,
            },
            "responses": [{"response": last_response}],
        }
        output_cases.append(case_trace)

    output_dataset = {"eval_cases": output_cases}

    with open(output_path, "w") as f:
        json.dump(output_dataset, f, indent=2)

    print(f"Successfully generated evaluation traces and saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(generate_traces())
