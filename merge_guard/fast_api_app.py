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

import base64
import contextlib
import json
import os
import uuid
from collections.abc import AsyncIterator

import google.auth
from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.cloud import logging as google_cloud_logging
from google.genai import types

from merge_guard.app_utils import services
from merge_guard.app_utils.a2a import attach_a2a_routes
from merge_guard.app_utils.reasoning_engine_adapter import (
    attach_reasoning_engine_routes,
)
from merge_guard.app_utils.telemetry import (
    setup_agent_engine_telemetry,
    setup_telemetry,
)
from merge_guard.app_utils.typing import Feedback

load_dotenv()
setup_telemetry()
# Must run before get_fast_api_app to set the tracer provider resource.
setup_agent_engine_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runner for the A2A path, sharing the same session/artifact services as the
    # adk_api and reasoning_engine paths (see services.py). Imported here so the
    # agent is built after env/telemetry setup.
    from merge_guard.agent import app as adk_app
    from merge_guard.agent import root_agent

    session_service = services.get_session_service()
    artifact_service = services.get_artifact_service()

    runner = Runner(
        app=adk_app,
        session_service=session_service,
        artifact_service=artifact_service,
        auto_create_session=True,
    )
    # Shared by the A2A path and the reasoning_engine adapter routes.
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name

    # Expose session service to trigger endpoints
    app.state.session_service = session_service

    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=False,
    lifespan=lifespan,
)
app.title = "merge-guard"
app.description = (
    "API for interacting with the MergeGuard PR Triage Agent (merge-guard)"
)


# Proxy routes so the Vertex AI Console Playground (reasoning_engine SDK) can
# talk to this agent alongside the native adk_api routes.
attach_reasoning_engine_routes(app)


# Custom Pub/Sub trigger endpoint
@app.post("/")
@app.post("/pubsub")
async def handle_pubsub_trigger(request: Request) -> dict:
    """Handles incoming Pub/Sub push messages, feeds them to the workflow, and returns the result."""
    try:
        req_json = await request.json()
    except Exception as e:
        logger.error("Failed to parse JSON body: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    logger.info("Received Pub/Sub event payload: %s", json.dumps(req_json))

    message = req_json.get("message")
    if not message:
        logger.error("Missing 'message' wrapper in Pub/Sub payload")
        raise HTTPException(status_code=400, detail="Missing 'message' wrapper")

    # 1. Decode base64 data
    data_base64 = message.get("data")
    decoded_data = None
    if data_base64:
        try:
            decoded_bytes = base64.b64decode(data_base64)
            decoded_str = decoded_bytes.decode("utf-8")
            try:
                decoded_data = json.loads(decoded_str)
            except json.JSONDecodeError:
                decoded_data = decoded_str
        except Exception as e:
            logger.error("Failed to decode base64 message data: %s", e)
            raise HTTPException(
                status_code=400, detail=f"Invalid base64 payload: {e}"
            ) from e

    # 2. Normalize fully-qualified subscription path to short name
    subscription = req_json.get(
        "subscription", "projects/local/subscriptions/ambient-pr-triage-sub"
    )
    short_sub_name = subscription.split("/")[-1]

    # Use normalized short name as user_id to keep session records clean and readable
    user_id = short_sub_name

    # 3. Create or resolve the session ID
    message_id = message.get("messageId", str(uuid.uuid4()))
    session_id = f"sub-session-{message_id}"

    logger.info(
        "Processing event. SubName (user_id): %s, SessionID: %s", user_id, session_id
    )

    # 4. Prepare inputs
    input_payload = {
        "message": {"data": decoded_data, "attributes": message.get("attributes", {})},
        "subscription": subscription,
    }

    new_message = types.Content(
        role="user", parts=[types.Part.from_text(text=json.dumps(input_payload))]
    )

    # 5. Fetch runner and services from app state
    runner = app.state.runner
    session_service = app.state.session_service

    # Create the session and run the workflow
    session = await session_service.create_session(
        app_name="merge_guard", user_id=user_id, session_id=session_id
    )

    events = []
    try:
        async for event in runner.run_async(
            new_message=new_message, user_id=user_id, session_id=session.id
        ):
            events.append(event)
    except Exception as e:
        logger.exception("Workflow execution failed")
        raise HTTPException(
            status_code=500, detail=f"Workflow execution failed: {e}"
        ) from e

    # Determine execution state (e.g. if paused at HITL step)
    paused = False
    final_output = None
    for ev in events:
        if hasattr(ev, "output") and ev.output is not None:
            final_output = ev.output
        if hasattr(ev, "content") and ev.content and ev.content.parts:
            for part in ev.content.parts:
                if (
                    part.function_call
                    and part.function_call.name == "adk_request_input"
                ):
                    paused = True

    status_str = "paused_for_hitl" if paused else "completed"
    logger.info("Event processed successfully. Workflow Status: %s", status_str)

    return {
        "status": "success",
        "session_id": session.id,
        "user_id": user_id,
        "workflow_status": status_str,
        "output": final_output,
    }


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
