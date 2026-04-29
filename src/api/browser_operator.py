"""
Browser Operator approval flow — Phase 2 backend.

Approval-only API: the frontend (or any caller) creates a *proposal* describing
a single, bounded browser action against an existing ``/api/browser`` session.
The operator then approves or denies it. On approval, this router dispatches
the action **in-process** against the existing :class:`BrowserSessionManager`,
bypassing the HTTP route-layer ``operator_mode_required`` 409 gate. There is no
spoofable header path; clients cannot bypass the gate by sending a query
parameter, header, or body field.

Hard scope (matching ``docs/capabilities/computer_control_pack_v1.md`` Phase 2):

* Browser only — no file/terminal/OS/app control.
* User-approved actions only — no autonomous proposer, no LLM-driven proposals.
* No MCP installation, no Hermes config mutation, no ``.ham/settings.json`` writes.
* No goHAM behavior, no ControlPlaneRun changes.
* Bounded, redacted proposal records (URL host+path, capped text; no secrets).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.browser_operator.dispatch import dispatch_approved_proposal
from src.persistence.browser_proposal import (
    ALLOWED_ACTION_TYPES,
    BrowserActionPayload,
    BrowserActionProposal,
    BrowserProposalStore,
    ProposerActor,
    new_proposal_id,
    utc_now_iso,
)


def _ttl_seconds() -> int:
    raw = (os.environ.get("HAM_BROWSER_OPERATOR_PROPOSAL_TTL_SECONDS") or "30").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 30


def _max_pending_per_session() -> int:
    raw = (os.environ.get("HAM_BROWSER_OPERATOR_MAX_PENDING_PER_SESSION") or "8").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 8


def _utc_iso_in(seconds: int) -> str:
    """ISO-8601 UTC ``Z`` timestamp in :func:`utc_now_iso` shape, offset by ``seconds``."""
    dt = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=int(seconds))
    return dt.isoformat().replace("+00:00", "Z")


def _is_expired(proposal: BrowserActionProposal) -> bool:
    return proposal.expires_at <= utc_now_iso()


_store_singleton: BrowserProposalStore | None = None


def get_browser_proposal_store() -> BrowserProposalStore:
    """Lazy singleton; tests can monkeypatch this attribute on the module."""
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = BrowserProposalStore()
    return _store_singleton


router = APIRouter(
    prefix="/api/browser-operator",
    tags=["browser-operator"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateProposalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    owner_key: str = Field(min_length=1, max_length=128)
    action: BrowserActionPayload
    proposer: ProposerActor | None = None

    @model_validator(mode="after")
    def _v_action_required_fields(self) -> CreateProposalBody:
        a = self.action
        t = a.action_type
        if t not in ALLOWED_ACTION_TYPES:
            raise ValueError(f"unsupported action_type: {t}")
        if t == "browser.navigate" and not (a.url and a.url.strip()):
            raise ValueError("browser.navigate requires url")
        if t == "browser.click_xy" and (a.x is None or a.y is None):
            raise ValueError("browser.click_xy requires x and y")
        if t == "browser.key" and not (a.key and a.key.strip()):
            raise ValueError("browser.key requires key")
        if t == "browser.type" and not (a.selector and a.selector.strip()):
            raise ValueError("browser.type requires selector")
        return self


class ApproveDenyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_key: str = Field(min_length=1, max_length=128)
    note: str | None = None


# ---------------------------------------------------------------------------
# Public payload shape
# ---------------------------------------------------------------------------


def _public(p: BrowserActionProposal) -> dict[str, Any]:
    d = p.model_dump(mode="json", exclude_none=True)
    d["kind"] = "browser_action_proposal"
    return d


def _http_owner_or_404(
    proposal_id: str, owner_key: str
) -> BrowserActionProposal:
    store = get_browser_proposal_store()
    proposal = store.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    if proposal.owner_key != owner_key:
        raise HTTPException(status_code=403, detail="proposal owner mismatch")
    return proposal


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/policy")
def browser_operator_policy() -> dict[str, Any]:
    return {
        "kind": "browser_operator_policy",
        "approval_only": True,
        "allowed_action_types": sorted(ALLOWED_ACTION_TYPES),
        "ttl_seconds": _ttl_seconds(),
        "max_pending_per_session": _max_pending_per_session(),
        "dispatch_mode": "in_process_manager_call",
        "header_unlock_supported": False,
    }


@router.post("/proposals")
def create_browser_proposal(body: CreateProposalBody) -> dict[str, Any]:
    sid = body.session_id.strip()
    ok = body.owner_key.strip()
    store = get_browser_proposal_store()
    pending = store.count_pending_for_session(session_id=sid, owner_key=ok)
    if pending >= _max_pending_per_session():
        raise HTTPException(status_code=429, detail="too many pending proposals for this session")

    now_iso = utc_now_iso()
    expires_iso = _utc_iso_in(_ttl_seconds())

    proposal = BrowserActionProposal(
        proposal_id=new_proposal_id(),
        session_id=sid,
        owner_key=ok,
        state="proposed",
        action=body.action,
        proposer=body.proposer or ProposerActor(),
        created_at=now_iso,
        expires_at=expires_iso,
    )
    store.save(proposal)
    return _public(proposal)


@router.get("/proposals")
def list_browser_proposals(
    session_id: Annotated[str, Query(min_length=1, max_length=128)],
    owner_key: Annotated[str, Query(min_length=1, max_length=128)],
    limit: Annotated[int, Query(ge=1, le=200)] = 64,
) -> dict[str, Any]:
    sid = session_id.strip()
    ok = owner_key.strip()
    store = get_browser_proposal_store()
    rows = store.list_for_session(session_id=sid, owner_key=ok, limit=limit)
    return {
        "kind": "browser_action_proposal_list",
        "session_id": sid,
        "items": [_public(r) for r in rows],
    }


@router.get("/proposals/{proposal_id}")
def get_browser_proposal(
    proposal_id: str,
    owner_key: Annotated[str, Query(min_length=1, max_length=128)],
) -> dict[str, Any]:
    proposal = _http_owner_or_404(proposal_id, owner_key.strip())
    return _public(proposal)


@router.post("/proposals/{proposal_id}/deny")
def deny_browser_proposal(proposal_id: str, body: ApproveDenyBody) -> dict[str, Any]:
    ok = body.owner_key.strip()
    proposal = _http_owner_or_404(proposal_id, ok)
    if proposal.state != "proposed":
        raise HTTPException(status_code=409, detail=f"proposal not pending (state={proposal.state})")
    if _is_expired(proposal):
        proposal = proposal.model_copy(update={"state": "expired"})
        get_browser_proposal_store().save(proposal)
        raise HTTPException(status_code=410, detail="proposal expired")

    updated = proposal.model_copy(
        update={
            "state": "denied",
            "decided_at": utc_now_iso(),
            "decision_note": body.note,
        }
    )
    get_browser_proposal_store().save(updated)
    return _public(updated)


@router.post("/proposals/{proposal_id}/approve")
def approve_browser_proposal(proposal_id: str, body: ApproveDenyBody) -> dict[str, Any]:
    ok = body.owner_key.strip()
    store = get_browser_proposal_store()
    proposal = _http_owner_or_404(proposal_id, ok)

    # Terminal states cannot be approved (one-shot semantics).
    if proposal.state != "proposed":
        raise HTTPException(status_code=409, detail=f"proposal not pending (state={proposal.state})")

    if _is_expired(proposal):
        expired = proposal.model_copy(update={"state": "expired"})
        store.save(expired)
        raise HTTPException(status_code=410, detail="proposal expired")

    # Move to ``approved`` *before* dispatch so a concurrent re-approve cannot
    # double-execute. This is best-effort without a DB lock; suitable for v1.
    approved = proposal.model_copy(
        update={
            "state": "approved",
            "decided_at": utc_now_iso(),
            "decision_note": body.note,
        }
    )
    store.save(approved)

    result = dispatch_approved_proposal(approved)
    if result.ok:
        executed = approved.model_copy(
            update={
                "state": "executed",
                "executed_at": utc_now_iso(),
                "result_status": "ok",
                "result_last_error": None,
            }
        )
        store.save(executed)
        return _public(executed)

    failed = approved.model_copy(
        update={
            "state": "failed",
            "executed_at": utc_now_iso(),
            "result_status": "error",
            "result_last_error": result.error_message,
        }
    )
    store.save(failed)
    # Surface the most useful HTTP status for the failure kind.
    code = {
        "not_found": 404,
        "owner_mismatch": 403,
        "policy": 422,
        "conflict": 409,
        "runtime": 400,
        "unsupported_action": 422,
    }.get(result.error_kind or "unknown", 500)
    raise HTTPException(status_code=code, detail={"proposal": _public(failed), "kind": result.error_kind})


__all__ = [
    "approve_browser_proposal",
    "browser_operator_policy",
    "create_browser_proposal",
    "deny_browser_proposal",
    "get_browser_proposal_store",
    "list_browser_proposals",
    "router",
]
