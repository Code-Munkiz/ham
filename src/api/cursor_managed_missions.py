"""Read-only API for HAM :class:`ManagedMission` (managed Cloud Agent mission history)."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import HamActor
from src.integrations.cursor_cloud_client import (
    CursorCloudApiError,
    cursor_api_cancel_agent,
    cursor_api_followup_agent,
)
from src.persistence.cursor_credentials import get_effective_cursor_api_key
from src.persistence.managed_mission import ManagedMission, ManagedMissionStore
from src.persistence.control_plane_run import utc_now_iso
from src.persistence.managed_mission import append_mission_feed_event

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)

_store = ManagedMissionStore()

router = APIRouter(
    prefix="/api/cursor/managed",
    tags=["cursor-managed-missions"],
)


class MissionMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


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


def _mission_feed_events(m: ManagedMission) -> list[dict[str, Any]]:
    events = [
        {
            "id": e.event_id,
            "time": e.observed_at,
            "kind": e.kind,
            "source": e.source,
            "message": e.message,
            "reason_code": e.reason_code,
        }
        for e in m.mission_feed_events
    ]
    if events:
        return events[-80:]
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
    return synth[-80:]


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
    return d


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


@router.get("/missions/{mission_registry_id}/feed")
async def get_managed_mission_feed(
    mission_registry_id: str,
    _actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
) -> dict[str, Any]:
    m = _get_mission_or_404(mission_registry_id)
    artifacts: list[dict[str, str]] = []
    if m.pr_url_last_observed:
        artifacts.append(
            {
                "kind": "pull_request",
                "title": "Pull request",
                "url": m.pr_url_last_observed,
            }
        )
    return {
        "mission_id": m.mission_registry_id,
        "provider": "cursor",
        "status": m.cursor_status_last_observed or m.mission_lifecycle,
        "lifecycle": m.mission_lifecycle,
        "repo": m.repository_observed,
        "ref": m.ref_observed,
        "latest_checkpoint": m.mission_checkpoint_latest,
        "updated_at": m.last_server_observed_at,
        "events": _mission_feed_events(m),
        "artifacts": artifacts,
        "pr_url": m.pr_url_last_observed,
        "cancel_supported": False,
    }


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
