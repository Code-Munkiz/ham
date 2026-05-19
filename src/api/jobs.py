"""Phase 2 — Per-job SSE stream: GET /api/jobs/<job_id>/stream.

Streams SSEEvents from BuilderRunEventsStore to the browser.
Honors Last-Event-ID for reconnect (ADR-0002).
Sends a 15s heartbeat when idle.
Closes the stream when the job reaches a terminal status.

Same Clerk/session auth as other builder control-plane routes.

Spec: docs/PHASE_2_DESIGN.md § Per-job SSE API route
ADR: docs/adr/0002-sse-with-replay-for-worker-events.md
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import Annotated

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.builder_plan import SSEEvent
from src.ham.clerk_auth import HamActor
from src.persistence.builder_run_events_store import (
    BuilderRunEventsStoreProtocol,
    get_builder_run_events_store,
)
from src.persistence.builder_runtime_job_store import (
    BuilderRuntimeJobStoreProtocol,
    get_builder_runtime_job_store,
)

_LOG = logging.getLogger(__name__)

router = APIRouter(tags=["builder-jobs"])

# Terminal statuses — stream closes when job reaches one of these
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

# SSE heartbeat interval (seconds) per Phase 0 Contract 4 / ADR-0002
_HEARTBEAT_INTERVAL = 15

# Polling interval when no new events (seconds)
_POLL_INTERVAL = 0.5


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sse_line(event_type: str, data: str, *, event_id: str | None = None) -> str:
    """Format a single SSE frame."""
    parts: list[str] = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event_type}")
    parts.append(f"data: {data}")
    parts.append("")  # blank line terminates the frame
    parts.append("")
    return "\n".join(parts)


def _heartbeat_frame() -> str:
    """SSE heartbeat frame (in-band, not a real SSEEvent)."""
    return _sse_line("heartbeat", json.dumps({"type": "heartbeat", "ts": _utc_now_iso()}))


def _event_frame(event: SSEEvent) -> str:
    """Serialize an SSEEvent to an SSE frame."""
    return _sse_line(
        event.event.type,  # type: ignore[union-attr]
        event.model_dump_json(),
        event_id=str(event.seq),
    )


async def _stream_events(
    job_id: str,
    *,
    since_seq: int,
    events_store: BuilderRunEventsStoreProtocol,
    job_store: BuilderRuntimeJobStoreProtocol,
    workspace_id: str | None,
    project_id: str | None,
) -> AsyncGenerator[str, None]:
    """Async generator that streams SSE frames for a job.

    Polls the events store, emits new events, sends heartbeats when idle,
    and closes when the job reaches terminal status.
    """
    last_seq = since_seq
    idle_ticks = 0

    while True:
        # --- Fetch new events since last_seq ---
        try:
            new_events = events_store.read_from(job_id=job_id, since_seq=last_seq)
        except Exception as exc:
            _LOG.warning("stream_events: read_from failed for %s: %s", job_id, exc)
            new_events = []

        for event in new_events:
            yield _event_frame(event)
            last_seq = event.seq
            idle_ticks = 0

        # --- Check job terminal status ---
        job = None
        if workspace_id and project_id:
            try:
                job = job_store.get_cloud_runtime_job(
                    workspace_id=workspace_id,
                    project_id=project_id,
                    job_id=job_id,
                )
            except Exception as exc:
                _LOG.warning("stream_events: job_store read failed for %s: %s", job_id, exc)

        if job is not None and job.status in _TERMINAL_STATUSES:
            # Drain any remaining events that might have landed after the
            # terminal status was set.
            try:
                remaining = events_store.read_from(job_id=job_id, since_seq=last_seq)
            except Exception:
                remaining = []
            for event in remaining:
                yield _event_frame(event)
                last_seq = event.seq
            _LOG.info("stream_events: job %s reached terminal status %s — closing stream", job_id, job.status)
            return

        # --- Heartbeat when idle ---
        idle_ticks += 1
        ticks_per_heartbeat = max(1, int(_HEARTBEAT_INTERVAL / _POLL_INTERVAL))
        if idle_ticks >= ticks_per_heartbeat:
            yield _heartbeat_frame()
            idle_ticks = 0

        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/api/jobs/{job_id}/stream")
async def stream_job_events(
    job_id: str,
    request: Request,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Stream SSEEvents for a specific job.

    Query params:
        (none)

    Headers:
        Last-Event-ID: <seq> — resume from this sequence number (ADR-0002)

    Response: text/event-stream
    """
    # --- Parse since_seq from Last-Event-ID ---
    since_seq = 0
    if last_event_id is not None:
        try:
            since_seq = max(0, int(last_event_id))
        except (ValueError, TypeError):
            since_seq = 0

    events_store = get_builder_run_events_store()
    job_store = get_builder_runtime_job_store()

    # --- Find the job (workspace_id + project_id required for scoped lookup) ---
    # We do a broad search: load from the store directly via job_id.
    # The store protocol only supports (workspace_id, project_id, job_id),
    # so we rely on the job metadata if workspace context is not in the URL.
    workspace_id: str | None = None
    project_id: str | None = None

    # Try to find job in store via query params if provided
    ws_param = request.query_params.get("workspace_id")
    proj_param = request.query_params.get("project_id")
    if ws_param and proj_param:
        workspace_id = ws_param
        project_id = proj_param
        job = job_store.get_cloud_runtime_job(
            workspace_id=workspace_id,
            project_id=project_id,
            job_id=job_id,
        )
    else:
        # Attempt a broad scan via a helper if available
        job = _find_job_by_id(job_id, job_store=job_store)
        if job is not None:
            workspace_id = job.workspace_id
            project_id = job.project_id

    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"Job {job_id!r} not found.",
                }
            },
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        async for frame in _stream_events(
            job_id,
            since_seq=since_seq,
            events_store=events_store,
            job_store=job_store,
            workspace_id=workspace_id,
            project_id=project_id,
        ):
            # Respect client disconnect
            if await request.is_disconnected():
                _LOG.info("stream_job_events: client disconnected from job %s", job_id)
                return
            yield frame

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _find_job_by_id(
    job_id: str,
    *,
    job_store: BuilderRuntimeJobStoreProtocol,
) -> Any | None:
    """Best-effort scan for a job by id across all workspaces.

    The BuilderRuntimeJobStore protocol only supports (workspace_id,
    project_id, job_id) lookups.  A direct-id scan requires access to the
    underlying raw store.  For stores that expose get_cloud_runtime_job_by_id
    we use that; otherwise we fall back to None and require callers to supply
    workspace_id + project_id as query params.
    """
    if hasattr(job_store, "get_cloud_runtime_job_by_id"):
        return job_store.get_cloud_runtime_job_by_id(job_id=job_id)  # type: ignore[attr-defined]
    # For the file-backed store, try a raw scan via the private _load_raw path
    # only if we have a BuilderRuntimeJobStore instance.
    try:
        from src.persistence.builder_runtime_job_store import BuilderRuntimeJobStore
        from pydantic import ValidationError as PydanticValidationError

        if isinstance(job_store, BuilderRuntimeJobStore):
            raw = job_store._load_raw()
            from src.persistence.builder_runtime_job_store import CloudRuntimeJob
            for item in raw.get("cloud_runtime_jobs", []):
                if str(item.get("id") or "") == job_id:
                    try:
                        return CloudRuntimeJob.model_validate(
                            BuilderRuntimeJobStore._normalize_legacy_record(item)
                        )
                    except PydanticValidationError:
                        continue
    except Exception:  # noqa: BLE001
        pass
    return None
