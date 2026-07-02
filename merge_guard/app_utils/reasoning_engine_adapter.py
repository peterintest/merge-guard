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

"""Serve the reasoning_engine ``{class_method, input}`` contract over HTTP.

Exists to guarantee support for the Vertex AI Console Playground and Gemini
Enterprise (via ADK registration), which both invoke the engine through this
contract. Agent Engine forwards calls to ``/api/reasoning_engine`` (sync) and
``/api/stream_reasoning_engine`` (streaming); dispatch is limited to the
:class:`AdkApp` ``register_operations()`` methods so the wire output matches a
packaged Agent Engine.
"""

import inspect
import json

from fastapi import FastAPI, HTTPException, Request, encoders, responses
from vertexai.agent_engines.templates.adk import AdkApp

from merge_guard.app_utils import services


def attach_reasoning_engine_routes(app: FastAPI) -> None:
    """Register reasoning_engine routes that dispatch to an AdkApp."""
    runtime: AdkApp | None = None
    streaming_methods: set[str] = set()
    sync_methods: set[str] = set()

    def get_runtime() -> AdkApp:
        nonlocal runtime, streaming_methods, sync_methods
        if runtime is None:
            from merge_guard.agent import app as adk_app

            # Reuse the process-wide services so sessions created here are
            # visible to the adk_api and A2A paths, and vice versa (see services.py).
            runtime = AdkApp(
                app=adk_app,
                session_service_builder=services.get_session_service,
                artifact_service_builder=services.get_artifact_service,
            )
            runtime.set_up()

            # Enable auto-creation of sessions inside the standard ADK runner
            # to handle incoming Pub/Sub webhooks correctly.
            if "runner" in runtime._tmpl_attrs:
                runtime._tmpl_attrs["runner"].auto_create_session = True
            if "in_memory_runner" in runtime._tmpl_attrs:
                runtime._tmpl_attrs["in_memory_runner"].auto_create_session = True

            operations = runtime.register_operations()
            streaming_methods = set(operations.get("stream", [])) | set(
                operations.get("async_stream", [])
            )
            sync_methods = set(operations.get("", [])) | set(
                operations.get("async", [])
            )
        return runtime

    def resolve_method(class_method: str, *, streaming: bool):
        rt = get_runtime()
        allowed = streaming_methods if streaming else sync_methods
        if class_method not in allowed:
            raise HTTPException(
                status_code=404,
                detail=f"Unsupported reasoning_engine method: {class_method!r}",
            )
        return getattr(rt, class_method)

    @app.post("/api/stream_reasoning_engine")
    async def stream_query(request: Request) -> responses.StreamingResponse:
        import uuid

        body = await request.json()
        class_method = body.get("class_method") or "async_stream_query"
        method = resolve_method(class_method, streaming=True)
        kwargs = body.get("input") or {}

        # Resolve user_id and session_id from inputs, headers, or query parameters
        if "user_id" not in kwargs:
            kwargs["user_id"] = (
                kwargs.get("userId")
                or request.headers.get("x-vertex-user-id")
                or request.query_params.get("userId")
                or request.query_params.get("user_id")
                or "pubsub-push"
            )
        if "session_id" not in kwargs:
            kwargs["session_id"] = (
                kwargs.get("sessionId")
                or request.headers.get("x-vertex-session-id")
                or request.query_params.get("sessionId")
                or request.query_params.get("session_id")
                or f"sub-session-{uuid.uuid4()}"
            )

        # Remove redundant keys to prevent duplicate argument errors
        kwargs.pop("userId", None)
        kwargs.pop("sessionId", None)

        # Ensure session exists in the session service before running the query
        session_service = services.get_session_service()
        try:
            await session_service.get_session(
                app_name="merge_guard",
                user_id=kwargs["user_id"],
                session_id=kwargs["session_id"],
            )
        except Exception:
            await session_service.create_session(
                session_id=kwargs["session_id"],
                user_id=kwargs["user_id"],
                app_name="merge_guard",
            )

        async def generator():
            async for event in method(**kwargs):
                yield json.dumps(event) + "\n"

        return responses.StreamingResponse(
            content=generator(), media_type="application/json"
        )

    @app.post("/api/reasoning_engine")
    async def query(request: Request) -> responses.JSONResponse:
        import uuid

        body = await request.json()
        class_method = body.get("class_method") or "async_query"
        method = resolve_method(class_method, streaming=False)
        kwargs = body.get("input") or {}

        # Resolve user_id and session_id from inputs, headers, or query parameters
        if "user_id" not in kwargs:
            kwargs["user_id"] = (
                kwargs.get("userId")
                or request.headers.get("x-vertex-user-id")
                or request.query_params.get("userId")
                or request.query_params.get("user_id")
                or "pubsub-push"
            )
        if "session_id" not in kwargs:
            kwargs["session_id"] = (
                kwargs.get("sessionId")
                or request.headers.get("x-vertex-session-id")
                or request.query_params.get("sessionId")
                or request.query_params.get("session_id")
                or f"sub-session-{uuid.uuid4()}"
            )

        kwargs.pop("userId", None)
        kwargs.pop("sessionId", None)

        # Ensure session exists in the session service before running the query
        session_service = services.get_session_service()
        try:
            await session_service.get_session(
                app_name="merge_guard",
                user_id=kwargs["user_id"],
                session_id=kwargs["session_id"],
            )
        except Exception:
            await session_service.create_session(
                session_id=kwargs["session_id"],
                user_id=kwargs["user_id"],
                app_name="merge_guard",
            )

        output = (
            await method(**kwargs)
            if inspect.iscoroutinefunction(method)
            else method(**kwargs)
        )
        return responses.JSONResponse(
            content=encoders.jsonable_encoder({"output": output})
        )

    # Reorder routes so our custom /api/stream_reasoning_engine and /api/reasoning_engine are matched first
    custom_routes = []
    other_routes = []
    for r in app.router.routes:
        if getattr(r, "path", None) in ("/api/stream_reasoning_engine", "/api/reasoning_engine"):
            if r.endpoint.__module__.endswith("reasoning_engine_adapter"):
                custom_routes.append(r)
            else:
                other_routes.append(r)
        else:
            other_routes.append(r)
    app.router.routes = custom_routes + other_routes
