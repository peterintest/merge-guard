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

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from merge_guard.agent import root_agent


def test_agent_stream() -> None:
    """
    Integration test for the agent stream functionality.
    Tests that the agent returns valid streaming responses.
    """

    session_service = InMemorySessionService()

    session = session_service.create_session_sync(
        user_id="test_user", app_name="merge_guard"
    )
    runner = Runner(
        agent=root_agent, session_service=session_service, app_name="merge_guard"
    )

    # Send a valid PullRequestEvent payload as text to prevent parsing errors
    message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(text='{"repository": "google/adk", "pr_number": 101}')
        ],
    )

    events = list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )
    assert len(events) > 0, "Expected at least one event"

    # Verify that the final output event contains the TriageDecisionOutput
    final_event = events[-1]
    assert final_event.output is not None, "Expected final event output to not be None"

    output_data = final_event.output
    if isinstance(output_data, dict):
        assert output_data.get("decision") == "approved"
        assert output_data.get("risk_level") == "low"
    else:
        assert output_data.decision == "approved"
        assert output_data.risk_level == "low"
