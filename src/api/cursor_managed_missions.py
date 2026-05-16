"""Read-only API for HAM :class:`ManagedMission` (managed Cloud Agent mission history)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor, resolve_ham_operator_authorization_header
from src.ham.cursor_provider_adapter import (
    map_cursor_conversation_to_feed_events,
    map_cursor_sdk_bridge_to_feed_events,
    provider_capability_matrix,
    provider_projection_envelope,
)
from src.ham.managed_mission_truth import (
    managed_mission_correlation,
    managed_mission_truth_table,
)
from src.ham.managed_mission_wiring import (
    get_managed_mission_store,
    observe_mission_from_cursor_payload,
)
from src.hermes_feedback import HermesReviewer
from src.integrations.cursor_cloud_client import (
    CursorCloudApiError,
    cursor_api_cancel_agent,
    cursor_api_followup_agent,
    cursor_api_get_agent,
    cursor_api_get_agent_conversation,
)
from src.integrations.cursor_sdk_bridge_client import (
    cursor_sdk_bridge_enabled,
    iter_cursor_sdk_bridge_stdout_rows,
    stream_cursor_sdk_bridge_events,
)
from src.persistence.cursor_credentials import get_effective_cursor_api_key
from src.persistence.control_plane_run import (
    get_control_plane_run_store,
    set_control_plane_run_store_for_tests as _set_global_cp_store_for_tests,
    utc_now_iso,
)
from src.persistence.managed_mission import (
    ManagedMission,
    ManagedMissionStore,
    MissionFeedEvent,
    append_mission_feed_event,
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)

_MAX_MISSION_REVIEW_FEED_LINES = 40
_MAX_MISSION_REVIEW_CODE_CHARS = 2_000
_MAX_MISSION_REVIEW_CONTEXT_CHARS = 6_000
_MISSION_HERMES_STALE_SECONDS_DEFAULT = 900

_store = ManagedMissionStore()


def set_control_plane_run_store_for_tests(store: object | None) -> None:
    """Test hook: delegates to the global control-plane run store singleton so that
    managed-mission correlation and the read API both see the same injected store."""
    _set_global_cp_store_for_tests(store)  # type: ignore[arg-type]


def _control_plane_store():  # type: ignore[return]
    return get_control_plane_run_store()


def _require_managed_mission_write_token(authorization: str | None) -> None:
    expected = (os.environ.get("HAM_MANAGED_MISSION_WRITE_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "MANAGED_MISSION_WRITES_DISABLED",
                    "message": "Set HAM_MANAGED_MISSION_WRITE_TOKEN to enable board-state and Hermes advisory writes.",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "MANAGED_MISSION_AUTH_REQUIRED",
                    "message": "Authorization: Bearer <HAM_MANAGED_MISSION_WRITE_TOKEN> required.",
                }
            },
        )
    got = authorization[7:].strip()
    if got != expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "MANAGED_MISSION_AUTH_INVALID",
                    "message": "Invalid managed mission write token.",
                }
            },
        )


def _hermes_advisory_stale_seconds() -> int:
    raw = (os.environ.get("HAM_MANAGED_MISSION_HERMES_STALE_SECONDS") or "").strip()
    try:
        n = int(raw) if raw else _MISSION_HERMES_STALE_SECONDS_DEFAULT
    except ValueError:
        n = _MISSION_HERMES_STALE_SECONDS_DEFAULT
    return max(60, min(n, 86400))


def _iso_to_epoch_seconds(iso: str | None) -> float | None:
    if not iso or not str(iso).strip():
        return None
    s = str(iso).strip()
    try:
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
        else:
            s2 = s
        return datetime.fromisoformat(s2).timestamp()
    except ValueError:
        return None


def _hermes_advisory_is_stale(m: ManagedMission) -> bool:
    ts = _iso_to_epoch_seconds(m.hermes_advisory_triggered_at)
    if ts is None:
        return False
    return (time.time() - ts) >= float(_hermes_advisory_stale_seconds())


def _build_mission_review_artifact(m: ManagedMission) -> tuple[str, str]:
    lines: list[str] = []
    tail = m.mission_feed_events[-_MAX_MISSION_REVIEW_FEED_LINES:]
    for ev in tail:
        lines.append(f"[{ev.kind}] {ev.message}")
    code = "\n".join(lines).strip() or "(no feed lines)"
    if len(code) > _MAX_MISSION_REVIEW_CODE_CHARS:
        code = code[: _MAX_MISSION_REVIEW_CODE_CHARS - 1] + "…"
    ctx_parts = [
        f"mission_registry_id={m.mission_registry_id}",
        f"cursor_agent_id={m.cursor_agent_id}",
        f"mission_lifecycle={m.mission_lifecycle}",
        f"cursor_status_last_observed={m.cursor_status_last_observed}",
        f"mission_checkpoint_latest={m.mission_checkpoint_latest}",
        f"repository_observed={m.repository_observed}",
        f"ref_observed={m.ref_observed}",
        f"pr_url_last_observed={m.pr_url_last_observed}",
    ]
    context = "\n".join(ctx_parts)
    if len(context) > _MAX_MISSION_REVIEW_CONTEXT_CHARS:
        context = context[: _MAX_MISSION_REVIEW_CONTEXT_CHARS - 1] + "…"
    return code, context

router = APIRouter(
    prefix="/api/cursor/managed",
    tags=["cursor-managed-missions"],
)


class MissionMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class MissionBoardStateBody(BaseModel):
    mission_board_state: Literal["backlog", "active", "archive"]


def _get_mission_or_404(mission_registry_id: str) -> ManagedMission:
    mid = mission_registry_id.strip()
    if not _UUID_RE.match(mid):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Mission not found."}},
        )
    m = _store.get(mid)
    if m is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Mission not found."}},
        )
    return m


def _mission_feed_row_from_event(e: MissionFeedEvent) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": e.event_id,
        "time": e.observed_at,
        "kind": e.kind,
        "source": e.source,
        "message": e.message,
        "reason_code": e.reason_code,
    }
    if e.metadata:
        d["metadata"] = e.metadata
    return d


def _mission_feed_events(m: ManagedMission) -> list[dict[str, Any]]:
    events = [_mission_feed_row_from_event(e) for e in m.mission_feed_events]
    if events:
        events_sorted = sorted(events, key=lambda x: (x.get("time") or "", x.get("id") or ""))
        return events_sorted[-80:]
    synth: list[dict[str, Any]] = [
        {
            "id": f"evt_{m.mission_registry_id[:8]}_created",
            "time": m.created_at,
            "kind": "mission_started",
            "source": "ham",
            "message": "HAM launched Cursor Cloud Agent.",
            "reason_code": "managed_launch_created",
        }
    ]
    for idx, ev in enumerate(m.mission_checkpoint_events):
        synth.append(
            {
                "id": f"evt_{m.mission_registry_id[:8]}_cp_{idx}",
                "time": ev.observed_at,
                "kind": "checkpoint",
                "source": "ham",
                "message": f"Checkpoint: {ev.checkpoint}",
                "reason_code": ev.reason,
            }
        )
    synth_sorted = sorted(synth, key=lambda x: (x.get("time") or "", x.get("id") or ""))
    return synth_sorted[-80:]


def _merge_provider_events(m: ManagedMission, events: list[dict[str, Any]]) -> ManagedMission:
    if not events:
        return m
    existing_ids = {e.event_id for e in m.mission_feed_events}
    merged = list(m.mission_feed_events)
    for ev in events:
        eid = str(ev.get("event_id") or "").strip()
        if not eid or eid in existing_ids:
            continue
        meta = ev.get("metadata")
        if meta is not None and not isinstance(meta, dict):
            meta = None
        merged = append_mission_feed_event(
            existing=merged,
            observed_at=str(ev.get("observed_at") or utc_now_iso()),
            kind=str(ev.get("kind") or "provider_event"),
            source=str(ev.get("source") or "cursor"),
            message=str(ev.get("message") or "Provider event"),
            reason_code=(
                str(ev.get("reason_code"))
                if ev.get("reason_code") not in (None, "")
                else None
            ),
            event_id=eid,
            metadata=meta,
        )
        existing_ids.add(eid)
    if len(merged) == len(m.mission_feed_events):
        return m
    n = utc_now_iso()
    return m.model_copy(
        update={
            "mission_feed_events": merged,
            "updated_at": n,
            "last_server_observed_at": n,
        }
    )


def _sync_provider_projection(m: ManagedMission) -> tuple[ManagedMission, str | None, str]:
    """
    Best-effort provider enrichment:
    - Refresh latest agent status payload
    - Project conversation/events into HAM feed
    """
    api_key = get_effective_cursor_api_key()
    if not api_key:
        return m, "provider_key_missing", "rest_projection"
    sdk_bridge_error: str | None = None
    if cursor_sdk_bridge_enabled():
        rows, sdk_err = stream_cursor_sdk_bridge_events(
            api_key=api_key,
            agent_id=m.cursor_agent_id,
            run_id=None,
            max_seconds=30,
        )
        if sdk_err is None:
            projected_sdk = map_cursor_sdk_bridge_to_feed_events(agent_id=m.cursor_agent_id, rows=rows)
            if projected_sdk:
                merged_sdk = _merge_provider_events(m, projected_sdk)
                if merged_sdk != m:
                    _store.save(merged_sdk)
                return merged_sdk, None, "sdk_stream_bridge"
            sdk_bridge_error = "provider_sdk_bridge_malformed_output"
        else:
            sdk_bridge_error = sdk_err
    try:
        raw_agent = cursor_api_get_agent(api_key=api_key, agent_id=m.cursor_agent_id)
        observe_mission_from_cursor_payload(raw=raw_agent)
        refreshed = get_managed_mission_store().get(m.mission_registry_id) or m
    except CursorCloudApiError as exc:
        if sdk_bridge_error:
            return m, sdk_bridge_error, "rest_projection"
        return m, f"provider_status_unavailable:{exc.status_code or 'unknown'}", "rest_projection"
    try:
        raw_conv = cursor_api_get_agent_conversation(
            api_key=api_key,
            agent_id=refreshed.cursor_agent_id,
        )
    except CursorCloudApiError as exc:
        if sdk_bridge_error:
            return refreshed, sdk_bridge_error, "rest_projection"
        return refreshed, f"provider_conversation_unavailable:{exc.status_code or 'unknown'}", "rest_projection"
    projected = map_cursor_conversation_to_feed_events(
        agent_id=refreshed.cursor_agent_id,
        payload=raw_conv if isinstance(raw_conv, dict) else None,
    )
    merged = _merge_provider_events(refreshed, projected)
    if merged != refreshed:
        _store.save(merged)
    return merged, sdk_bridge_error, "rest_projection"


def _public_mission(m: ManagedMission) -> dict[str, Any]:
    timeline: list[dict[str, Any]] = []
    timeline.append(
        {
            "kind": "lifecycle",
            "label": "Mission registered",
            "at": m.created_at,
            "value": m.mission_lifecycle,
        }
    )
    for e in m.mission_checkpoint_events:
        timeline.append(
            {
                "kind": "checkpoint",
                "label": f"Checkpoint: {e.checkpoint}",
                "at": e.observed_at,
                "value": e.reason,
            }
        )
    if m.updated_at and m.updated_at != m.created_at:
        timeline.append(
            {
                "kind": "sync",
                "label": "Mission updated",
                "at": m.updated_at,
                "value": m.status_reason_last_observed,
            }
        )
    artifacts: list[dict[str, str]] = []
    if m.pr_url_last_observed:
        artifacts.append(
            {
                "kind": "pull_request",
                "title": "Pull request",
                "url": m.pr_url_last_observed,
            }
        )
    task_summary = (
        m.last_review_headline
        or m.status_reason_last_observed
        or (f"Cloud Agent mission for {m.repository_observed}" if m.repository_observed else "Cloud Agent mission")
    )
    error_summary = None
    if m.mission_lifecycle == "failed":
        error_summary = m.last_post_deploy_reason_code or m.status_reason_last_observed or "Mission failed."
    d = m.model_dump(mode="json", exclude_none=False)
    d["provider"] = "cursor"
    d["title"] = task_summary
    d["task_summary"] = task_summary
    d["kind"] = "managed_mission"
    d["latest_checkpoint"] = m.mission_checkpoint_latest
    d["latest_checkpoint_at"] = m.mission_checkpoint_updated_at
    d["latest_checkpoint_reason"] = m.mission_checkpoint_reason_last
    d["progress_events"] = timeline[-24:]
    d["artifacts"] = artifacts
    d["outputs_available"] = bool(artifacts)
    d["cancel_supported"] = False
    d["error_summary"] = error_summary
    d["checkpoint_events"] = [
        e.model_dump(mode="json", exclude_none=False) for e in m.mission_checkpoint_events
    ]
    d["hermes_advisory_stale"] = _hermes_advisory_is_stale(m)
    return d


def _control_plane_public_subset(ham_run_id: str) -> dict[str, Any] | None:
    r = _control_plane_store().get(ham_run_id.strip())
    if r is None:
        return None
    return {
        "ham_run_id": r.ham_run_id,
        "provider": r.provider,
        "action_kind": r.action_kind,
        "project_id": r.project_id,
        "status": r.status,
        "status_reason": r.status_reason,
        "external_id": r.external_id,
        "summary": r.summary,
        "error_summary": r.error_summary,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "last_observed_at": r.last_observed_at,
        "last_provider_status": r.last_provider_status,
    }


def _compose_managed_mission_feed_bundle(m: ManagedMission) -> tuple[ManagedMission, dict[str, Any]]:
    """Single source of truth for GET /feed and SSE snapshot payloads."""
    m_syn, provider_error, provider_mode = _sync_provider_projection(m)
    native_stream = provider_mode == "sdk_stream_bridge" and provider_error is None
    artifacts: list[dict[str, str]] = []
    if m_syn.pr_url_last_observed:
        artifacts.append(
            {
                "kind": "pull_request",
                "title": "Pull request",
                "url": m_syn.pr_url_last_observed,
            }
        )
    bundle = {
        "mission_id": m_syn.mission_registry_id,
        "provider": "cursor",
        "status": m_syn.cursor_status_last_observed or m_syn.mission_lifecycle,
        "lifecycle": m_syn.mission_lifecycle,
        "repo": m_syn.repository_observed,
        "ref": m_syn.ref_observed,
        "latest_checkpoint": m_syn.mission_checkpoint_latest,
        "updated_at": m_syn.last_server_observed_at,
        "events": _mission_feed_events(m_syn),
        "artifacts": artifacts,
        "pr_url": m_syn.pr_url_last_observed,
        "cancel_supported": True,
        "provider_capabilities": provider_capability_matrix(),
        "provider_projection_state": "ok" if provider_error is None else "fallback",
        "provider_projection_reason": provider_error,
        "provider_projection": provider_projection_envelope(
            provider_error=provider_error,
            mode=provider_mode,
            native_realtime_stream=native_stream,
        ),
    }
    return m_syn, bundle


def _replay_persisted_event_rows_after(m: ManagedMission, after_event_id: str | None) -> list[dict[str, Any]]:
    rows = [_mission_feed_row_from_event(e) for e in m.mission_feed_events]
    rows.sort(key=lambda r: (r.get("time") or "", r.get("id") or ""))
    aid = str(after_event_id or "").strip()
    if not aid:
        return []
    idx = next((i for i, row in enumerate(rows) if row.get("id") == aid), None)
    if idx is None:
        return rows
    return rows[idx + 1 :]


def _is_managed_mission_terminal(m: ManagedMission) -> bool:
    return m.mission_lifecycle in ("succeeded", "failed", "archived")


def _sse_pack(event_name: str, payload: dict[str, Any]) -> bytes:
    return (
        f"event: {event_name}\ndata: "
        + json.dumps(payload, separators=(",", ":"), default=str)
        + "\n\n"
    ).encode("utf-8")


@router.get("/missions")
async def list_managed_missions(
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    limit: int = Query(50, ge=1, le=500, description="Max missions (newest by file mtime first)"),
    cursor_agent_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=512,
        description="When set, return at most one row for this Cursor agent if present",
    ),
) -> dict[str, Any]:
    if cursor_agent_id and str(cursor_agent_id).strip():
        ca = str(cursor_agent_id).strip()
        m = _store.find_by_cursor_agent_id(ca)
        rows = [m] if m else []
    else:
        rows = _store.list_newest_first(limit=limit)
    return {
        "kind": "managed_mission_list",
        "limit": limit,
        "missions": [_public_mission(x) for x in rows],
    }


@router.get("/missions/{mission_registry_id}")
async def get_managed_mission(
    mission_registry_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    m = _get_mission_or_404(mission_registry_id)
    return _public_mission(m)


@router.get("/missions/{mission_registry_id}/truth")
async def get_managed_mission_truth(
    mission_registry_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    m = _get_mission_or_404(mission_registry_id)
    return managed_mission_truth_table(m=m)


@router.get("/missions/{mission_registry_id}/correlation")
async def get_managed_mission_correlation(
    mission_registry_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    m = _get_mission_or_404(mission_registry_id)
    base = managed_mission_correlation(m=m)
    hid = m.control_plane_ham_run_id
    if hid and str(hid).strip():
        run = _control_plane_public_subset(str(hid))
        if run:
            base["control_plane_run"] = run
    return base


@router.patch("/missions/{mission_registry_id}/board")
async def patch_managed_mission_board(
    mission_registry_id: str,
    body: MissionBoardStateBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    authorization: Annotated[str | None, Header()] = None,
    x_ham_operator_authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_managed_mission_write_token(ham_bearer)
    m = _get_mission_or_404(mission_registry_id)
    n = utc_now_iso()
    m2 = m.model_copy(
        update={
            "mission_board_state": body.mission_board_state,
            "updated_at": n,
            "last_server_observed_at": n,
            "mission_feed_events": append_mission_feed_event(
                existing=m.mission_feed_events,
                observed_at=n,
                kind="board_state",
                source="ham",
                message=f"Board lane set to {body.mission_board_state}.",
                reason_code="mission_board_state_updated",
            ),
        }
    )
    _store.save(m2)
    return {"ok": True, "mission": _public_mission(m2)}


@router.post("/missions/{mission_registry_id}/hermes-advisory")
async def post_managed_mission_hermes_advisory(
    mission_registry_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    authorization: Annotated[str | None, Header()] = None,
    x_ham_operator_authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_managed_mission_write_token(ham_bearer)
    m = _get_mission_or_404(mission_registry_id)
    n = utc_now_iso()
    code, context = _build_mission_review_artifact(m)
    reviewer = HermesReviewer()
    result = reviewer.evaluate(code, context)
    notes_list = result.get("notes") if isinstance(result.get("notes"), list) else []
    notes_join = "; ".join(str(x).strip() for x in notes_list if str(x).strip())
    truncated = len(notes_join) > 1700
    notes_capped = (notes_join[:1700] + "…") if truncated else (notes_join or None)
    ok_val = result.get("ok")
    advisory_ok: bool | None
    if isinstance(ok_val, bool):
        advisory_ok = ok_val
    else:
        advisory_ok = None
    m2 = m.model_copy(
        update={
            "hermes_advisory_triggered_at": n,
            "hermes_advisory_ok": advisory_ok,
            "hermes_advisory_notes": notes_capped,
            "hermes_advisory_truncated": truncated,
            "last_review_headline": notes_capped[:400] if notes_capped else m.last_review_headline,
            "last_review_severity": ("advisory" if advisory_ok is not None else m.last_review_severity),
            "updated_at": n,
            "last_server_observed_at": n,
            "mission_feed_events": append_mission_feed_event(
                existing=m.mission_feed_events,
                observed_at=n,
                kind="hermes_advisory",
                source="ham",
                message="Hermes advisory review recorded (does not change provider lifecycle).",
                reason_code="hermes_advisory_recorded",
            ),
        }
    )
    _store.save(m2)
    return {
        "ok": True,
        "mission_id": m2.mission_registry_id,
        "hermes_advisory": {
            "triggered_at": m2.hermes_advisory_triggered_at,
            "ok": m2.hermes_advisory_ok,
            "notes": m2.hermes_advisory_notes,
            "truncated": m2.hermes_advisory_truncated,
        },
        "reviewer_result_keys": sorted(str(k) for k in result.keys()) if isinstance(result, dict) else [],
    }


@router.get("/missions/{mission_registry_id}/feed")
async def get_managed_mission_feed(
    mission_registry_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    m = _get_mission_or_404(mission_registry_id)
    _m2, bundle = _compose_managed_mission_feed_bundle(m)
    return bundle


@router.get("/missions/{mission_registry_id}/feed/stream")
async def stream_managed_mission_feed(
    mission_registry_id: str,
    request: Request,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    after_event_id: str | None = Query(default=None),
    last_event_id_hdr: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """
    SSE stream: snapshot + persisted replay + chunked SDK bridge events (HAM backend only).

    Consumers should prefer fetch + readable stream parsing so Clerk ``Authorization``
    behaves like REST ``/feed`` (cookies + bearer).
    """

    mid = mission_registry_id.strip()
    mission_base = _get_mission_or_404(mid)
    effective_after = (
        str(after_event_id or "").strip()
        or str(last_event_id_hdr or "").strip()
        or None
    )

    async def event_iter():  # noqa: ANN202
        """Async generator yielding ``text/event-stream`` frames as UTF-8 bytes."""
        m_live, snapshot = _compose_managed_mission_feed_bundle(mission_base)
        yield _sse_pack("snapshot", snapshot)
        for row in _replay_persisted_event_rows_after(m_live, effective_after):
            yield _sse_pack("mission_event", row)

        loop_tm = asyncio.get_running_loop()
        _max_sess = float(os.environ.get("HAM_MANAGED_FEED_SSE_SESSION_MAX_SECONDS") or "2700")
        session_deadline = loop_tm.time() + max(3.0, _max_sess)
        heartbeat_every = 15.0
        last_emit = loop_tm.time()
        last_slow_pull = 0.0
        slow_pull_interval = 30.0 if cursor_sdk_bridge_enabled() else 10.0
        notified_rest_fallback = False
        sdk_chunk_fail_logged = False

        while loop_tm.time() < session_deadline:
            if await request.is_disconnected():
                return

            cur = _store.get(mid)
            if cur is None:
                yield _sse_pack("error", {"code": "mission_missing"})
                return

            now = loop_tm.time()
            if now - last_emit >= heartbeat_every:
                yield _sse_pack(
                    "heartbeat",
                    {"t": utc_now_iso(), "lifecycle": cur.mission_lifecycle},
                )
                last_emit = now

            if _is_managed_mission_terminal(cur):
                yield _sse_pack(
                    "completed",
                    {"mission_id": mid, "lifecycle": cur.mission_lifecycle},
                )
                return

            api_key = get_effective_cursor_api_key()
            can_sdk = cursor_sdk_bridge_enabled() and bool(api_key)

            if now - last_slow_pull >= slow_pull_interval:
                def _pull_slow() -> tuple[ManagedMission, str | None, str]:
                    b = _store.get(mid)
                    if b is None:
                        raise LookupError(mid)
                    return _sync_provider_projection(b)

                try:
                    m_slow, sdk_err_slow, mode_slow = await asyncio.to_thread(_pull_slow)
                    last_slow_pull = now
                    before_ids_slow = {e.event_id for e in cur.mission_feed_events}
                    for ev in sorted(
                        m_slow.mission_feed_events,
                        key=lambda e: (e.observed_at, e.event_id),
                    ):
                        if ev.event_id not in before_ids_slow:
                            yield _sse_pack(
                                "mission_event",
                                _mission_feed_row_from_event(ev),
                            )
                            last_emit = loop_tm.time()
                    prov_err_env = sdk_err_slow if mode_slow != "sdk_stream_bridge" else None
                    enveloped = provider_projection_envelope(
                        provider_error=prov_err_env,
                        mode=mode_slow,
                        native_realtime_stream=mode_slow == "sdk_stream_bridge" and sdk_err_slow is None,
                    )
                    yield _sse_pack("provider_projection", enveloped)

                    cur = _store.get(mid) or m_slow

                    if not can_sdk and not notified_rest_fallback:
                        notified_rest_fallback = True
                        yield _sse_pack(
                            "fallback",
                            {
                                "mode": "rest_projection",
                                "reason": sdk_err_slow or "provider_key_missing_or_bridge_disabled",
                            },
                        )
                    elif can_sdk and (mode_slow != "sdk_stream_bridge" or sdk_err_slow) and not notified_rest_fallback:
                        notified_rest_fallback = True
                        yield _sse_pack(
                            "fallback",
                            {
                                "mode": "rest_projection",
                                "hint": sdk_err_slow or "sdk_projection_unavailable",
                            },
                        )
                except LookupError:
                    yield _sse_pack("error", {"code": "mission_missing"})
                    return

                if await request.is_disconnected():
                    return

            if can_sdk and cur is not None and not _is_managed_mission_terminal(cur):
                bridge_rows_seen = False
                try:
                    async for bridge_row in iter_cursor_sdk_bridge_stdout_rows(
                        api_key=api_key or "",
                        agent_id=cur.cursor_agent_id,
                        run_id=None,
                        max_seconds=25,
                    ):
                        inner = _store.get(mid)
                        if inner is None:
                            yield _sse_pack("error", {"code": "mission_missing"})
                            return
                        before_bridge = {e.event_id for e in inner.mission_feed_events}
                        projected_rows = map_cursor_sdk_bridge_to_feed_events(
                            agent_id=inner.cursor_agent_id,
                            rows=[bridge_row],
                        )
                        merged_b = _merge_provider_events(inner, projected_rows)
                        if merged_b != inner:
                            _store.save(merged_b)
                        refreshed = _store.get(mid)
                        if refreshed is None:
                            yield _sse_pack("error", {"code": "mission_missing"})
                            return

                        terminal_hit = False
                        for ev in refreshed.mission_feed_events:
                            if ev.event_id not in before_bridge:
                                yield _sse_pack(
                                    "mission_event",
                                    _mission_feed_row_from_event(ev),
                                )
                                terminal_hit |= ev.kind == "completed"
                                last_emit = loop_tm.time()
                        cur = refreshed
                        if terminal_hit:
                            yield _sse_pack(
                                "completed",
                                {
                                    "mission_id": mid,
                                    "lifecycle": refreshed.mission_lifecycle,
                                },
                            )
                            return
                        if _is_managed_mission_terminal(refreshed):
                            yield _sse_pack(
                                "completed",
                                {
                                    "mission_id": mid,
                                    "lifecycle": refreshed.mission_lifecycle,
                                },
                            )
                            return
                        if await request.is_disconnected():
                            return
                        bridge_rows_seen = True
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if not sdk_chunk_fail_logged:
                        yield _sse_pack("error", {"code": "sdk_stream_chunk_failed"})
                        sdk_chunk_fail_logged = True
                    bridge_rows_seen = True
                if not bridge_rows_seen:
                    await asyncio.sleep(2.0)
                await asyncio.sleep(0.06)
            elif not can_sdk and not notified_rest_fallback:
                await asyncio.sleep(min(12.0, heartbeat_every))

            await asyncio.sleep(0.08)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/missions/{mission_registry_id}/messages")
async def post_managed_mission_message(
    mission_registry_id: str,
    body: MissionMessageBody,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    m = _get_mission_or_404(mission_registry_id)
    msg = str(body.message or "").strip()
    if not msg:
        raise HTTPException(status_code=422, detail="message required")
    n = utc_now_iso()
    feed = append_mission_feed_event(
        existing=m.mission_feed_events,
        observed_at=n,
        kind="followup_instruction",
        source="user",
        message=f"Instruction: {msg}",
    )
    m2 = m.model_copy(
        update={
            "mission_feed_events": feed,
            "updated_at": n,
            "last_server_observed_at": n,
        }
    )
    reason_code: str | None = None
    provider_result: dict[str, Any] | None = None
    if m2.mission_lifecycle != "open":
        reason_code = "mission_not_active"
    else:
        api_key = get_effective_cursor_api_key()
        if not api_key:
            reason_code = "provider_followup_not_supported"
        else:
            try:
                provider_result = cursor_api_followup_agent(
                    api_key=api_key,
                    agent_id=m2.cursor_agent_id,
                    prompt_text=msg,
                )
                m2 = m2.model_copy(
                    update={
                        "mission_feed_events": append_mission_feed_event(
                            existing=m2.mission_feed_events,
                            observed_at=utc_now_iso(),
                            kind="followup_forwarded",
                            source="ham",
                            message="HAM forwarded instruction to Cursor.",
                            reason_code="followup_forwarded",
                        ),
                    }
                )
            except CursorCloudApiError as exc:
                if exc.status_code in (404, 405, 409, 422):
                    reason_code = "mission_followup_not_supported"
                else:
                    reason_code = "provider_followup_not_supported"
    if reason_code:
        m2 = m2.model_copy(
            update={
                "mission_feed_events": append_mission_feed_event(
                    existing=m2.mission_feed_events,
                    observed_at=utc_now_iso(),
                    kind="followup_rejected",
                    source="ham",
                    message="Follow-up could not be sent to provider.",
                    reason_code=reason_code,
                ),
            }
        )
    _store.save(m2)
    return {
        "ok": reason_code is None,
        "mission_id": m2.mission_registry_id,
        "reason_code": reason_code or "followup_forwarded",
        "provider_response": provider_result,
    }


@router.post("/missions/{mission_registry_id}/cancel")
async def post_managed_mission_cancel(
    mission_registry_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    m = _get_mission_or_404(mission_registry_id)
    n = utc_now_iso()
    m2 = m.model_copy(
        update={
            "mission_feed_events": append_mission_feed_event(
                existing=m.mission_feed_events,
                observed_at=n,
                kind="cancel_requested",
                source="user",
                message="Stop requested.",
            ),
            "updated_at": n,
            "last_server_observed_at": n,
        }
    )
    if m2.mission_lifecycle != "open":
        reason = "mission_not_active"
        m2 = m2.model_copy(
            update={
                "mission_feed_events": append_mission_feed_event(
                    existing=m2.mission_feed_events,
                    observed_at=utc_now_iso(),
                    kind="cancel_rejected",
                    source="ham",
                    message="Mission is not active; stop was not sent.",
                    reason_code=reason,
                ),
            }
        )
        _store.save(m2)
        return {"ok": False, "mission_id": m2.mission_registry_id, "reason_code": reason}
    api_key = get_effective_cursor_api_key()
    if not api_key:
        reason = "cancel_not_supported"
        m2 = m2.model_copy(
            update={
                "mission_feed_events": append_mission_feed_event(
                    existing=m2.mission_feed_events,
                    observed_at=utc_now_iso(),
                    kind="cancel_rejected",
                    source="ham",
                    message="Stop is not supported for this provider yet.",
                    reason_code=reason,
                ),
            }
        )
        _store.save(m2)
        return {"ok": False, "mission_id": m2.mission_registry_id, "reason_code": reason}
    try:
        cursor_api_cancel_agent(api_key=api_key, agent_id=m2.cursor_agent_id)
    except CursorCloudApiError as exc:
        reason = "cancel_not_supported" if exc.status_code in (404, 405, 409, 422) else "cancel_failed"
        m2 = m2.model_copy(
            update={
                "mission_feed_events": append_mission_feed_event(
                    existing=m2.mission_feed_events,
                    observed_at=utc_now_iso(),
                    kind="cancel_rejected",
                    source="ham",
                    message="Provider did not accept cancellation.",
                    reason_code=reason,
                ),
            }
        )
        _store.save(m2)
        return {"ok": False, "mission_id": m2.mission_registry_id, "reason_code": reason}
    m2 = m2.model_copy(
        update={
            "mission_feed_events": append_mission_feed_event(
                existing=m2.mission_feed_events,
                observed_at=utc_now_iso(),
                kind="cancel_accepted",
                source="cursor",
                message="Provider accepted cancellation request.",
                reason_code="cancel_requested",
            ),
            "status_reason_last_observed": "cancel_requested",
        }
    )
    _store.save(m2)
    return {"ok": True, "mission_id": m2.mission_registry_id, "status": "cancel_requested"}
