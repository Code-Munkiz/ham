"""Read / preview / apply / rollback API for the persisted Social Policy.

Mounted at ``/api/social/policy/*``. Mirrors :mod:`src.api.project_settings`
for the auth + token + revision-conflict pattern, but operates on the
single repo-scoped ``.ham/social_policy.json`` document.

Safety contract enforced here:

* Apply and rollback both require a valid ``HAM_SOCIAL_POLICY_WRITE_TOKEN``
  Bearer header **and** a confirmation phrase exactly matching one of the
  literal strings exported by :mod:`src.ham.social_policy`.
* Flipping ``live_autonomy_armed`` from ``False`` to ``True`` requires a
  *second* phrase (``LIVE_AUTONOMY_CONFIRMATION_PHRASE``) and additionally
  requires ``HAM_SOCIAL_LIVE_APPLY_TOKEN`` to be set in the env. The
  policy file alone never enables live autonomy; existing apply gates
  on top of the policy still need to clear independently.
* No outbound HTTP, no provider client, no scheduler, no daemon. The
  router only manipulates the JSON document and its backups/audits.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.ham.clerk_auth import resolve_ham_operator_authorization_header
from src.ham.social_policy import (
    APPLY_CONFIRMATION_PHRASE,
    LIVE_AUTONOMY_CONFIRMATION_PHRASE,
    ROLLBACK_CONFIRMATION_PHRASE,
    ApplyResult,
    PreviewResult,
    RollbackResult,
    SocialPolicyChanges,
    SocialPolicyWriteConflictError,
    apply_social_policy,
    list_audit_envelopes,
    list_backups,
    preview_social_policy,
    read_social_policy_document,
    revision_for_document,
    rollback_social_policy,
    social_policy_writes_enabled,
)
from src.ham.social_policy.schema import (
    DEFAULT_SOCIAL_POLICY,
    SOCIAL_POLICY_REL_PATH,
    SocialPolicy,
    policy_to_safe_dict,
)

router = APIRouter(prefix="/api/social/policy", tags=["social-policy"])


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: SocialPolicyChanges
    client_proposal_id: str | None = Field(default=None, max_length=128)


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: SocialPolicyChanges
    base_revision: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    confirmation_phrase: str = Field(min_length=1, max_length=128)
    live_autonomy_phrase: str | None = Field(default=None, max_length=128)
    client_proposal_id: str | None = Field(default=None, max_length=128)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backup_id: str = Field(min_length=1, max_length=180)
    confirmation_phrase: str = Field(min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Return the repo root.

    Tests pin ``HAM_SOCIAL_POLICY_PATH`` directly, so this always uses CWD;
    this matches the singleton-document contract called out in the spec.
    """
    return Path.cwd()


def _require_policy_write_token(authorization: str | None) -> None:
    expected = (os.environ.get("HAM_SOCIAL_POLICY_WRITE_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_WRITES_DISABLED",
                    "message": "Set HAM_SOCIAL_POLICY_WRITE_TOKEN to enable apply and rollback.",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_AUTH_REQUIRED",
                    "message": "Authorization: Bearer <HAM_SOCIAL_POLICY_WRITE_TOKEN> required.",
                }
            },
        )
    got = authorization[7:].strip()
    if got != expected:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_AUTH_INVALID",
                    "message": "Invalid social policy write token.",
                }
            },
        )


def _require_apply_phrase(phrase: str) -> None:
    if (phrase or "").strip() != APPLY_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_PHRASE_INVALID",
                    "message": (
                        "confirmation_phrase must match the apply phrase exactly. "
                        "See policy module constants."
                    ),
                }
            },
        )


def _require_rollback_phrase(phrase: str) -> None:
    if (phrase or "").strip() != ROLLBACK_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_ROLLBACK_PHRASE_INVALID",
                    "message": "confirmation_phrase must match the rollback phrase exactly.",
                }
            },
        )


def _require_live_autonomy_gate(
    *,
    live_autonomy_change: bool,
    live_phrase: str | None,
) -> None:
    if not live_autonomy_change:
        return
    if not (os.environ.get("HAM_SOCIAL_LIVE_APPLY_TOKEN") or "").strip():
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_LIVE_AUTONOMY_DISABLED",
                    "message": (
                        "HAM_SOCIAL_LIVE_APPLY_TOKEN is not set; live_autonomy_armed cannot flip."
                    ),
                }
            },
        )
    if (live_phrase or "").strip() != LIVE_AUTONOMY_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_LIVE_AUTONOMY_PHRASE_INVALID",
                    "message": (
                        "live_autonomy_phrase must match the arm phrase exactly when "
                        "flipping live_autonomy_armed."
                    ),
                }
            },
        )


def _safe_existing_policy(root: Path) -> tuple[SocialPolicy, dict[str, Any], str]:
    doc = read_social_policy_document(root)
    if not doc:
        policy = DEFAULT_SOCIAL_POLICY.model_copy(deep=True)
    else:
        try:
            policy = SocialPolicy.model_validate(doc)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "SOCIAL_POLICY_DOCUMENT_INVALID",
                        "message": f"On-disk policy is invalid: {exc}",
                    }
                },
            ) from exc
    return policy, doc, revision_for_document(doc)


def _preview_payload(
    result: PreviewResult,
    *,
    project_root: str,
    client_proposal_id: str | None,
) -> dict[str, Any]:
    return {
        "project_root": project_root,
        "client_proposal_id": client_proposal_id,
        "effective_before": result.effective_before,
        "effective_after": result.effective_after,
        "diff": result.diff,
        "warnings": result.warnings,
        "write_target": result.write_target,
        "proposal_digest": result.proposal_digest,
        "base_revision": result.base_revision,
        "live_autonomy_change": result.live_autonomy_change,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", dependencies=[Depends(get_ham_clerk_actor)])
async def get_social_policy() -> dict[str, Any]:
    """Return the current policy document, write target, and write-status flag."""
    root = _project_root()
    policy, doc, revision = _safe_existing_policy(root)
    return {
        "project_root": str(root.resolve()),
        "write_target": SOCIAL_POLICY_REL_PATH,
        "exists": bool(doc),
        "policy": policy_to_safe_dict(policy),
        "revision": revision,
        "writes_enabled": social_policy_writes_enabled(),
        "live_apply_token_present": bool(
            (os.environ.get("HAM_SOCIAL_LIVE_APPLY_TOKEN") or "").strip(),
        ),
        "read_only": True,
    }


@router.post("/preview", dependencies=[Depends(get_ham_clerk_actor)])
async def post_social_policy_preview(body: PreviewRequest) -> dict[str, Any]:
    root = _project_root()
    try:
        result = preview_social_policy(root, body.changes)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_PREVIEW_INVALID",
                    "message": str(exc),
                }
            },
        ) from exc
    return _preview_payload(
        result,
        project_root=str(root.resolve()),
        client_proposal_id=body.client_proposal_id,
    )


@router.post("/apply", dependencies=[Depends(get_ham_clerk_actor)])
async def post_social_policy_apply(
    body: ApplyRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_policy_write_token(ham_bearer)
    _require_apply_phrase(body.confirmation_phrase)

    root = _project_root()
    # Compute the live-autonomy delta against the currently-stored doc; this
    # informs the second-phrase gate without trusting the client's flag alone.
    try:
        preview = preview_social_policy(root, body.changes)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_APPLY_INVALID",
                    "message": str(exc),
                }
            },
        ) from exc
    _require_live_autonomy_gate(
        live_autonomy_change=preview.live_autonomy_change,
        live_phrase=body.live_autonomy_phrase,
    )

    try:
        result: ApplyResult = apply_social_policy(
            root,
            body.changes,
            base_revision=body.base_revision,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_APPLY_INVALID",
                    "message": str(exc),
                }
            },
        ) from exc
    except SocialPolicyWriteConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_REVISION_CONFLICT",
                    "message": str(exc),
                }
            },
        ) from exc
    return {
        "project_root": str(root.resolve()),
        "backup_id": result.backup_id,
        "audit_id": result.audit_id,
        "effective_after": result.effective_after,
        "diff_applied": result.diff_applied,
        "new_revision": result.new_revision,
        "live_autonomy_change": result.live_autonomy_change,
    }


@router.post("/rollback", dependencies=[Depends(get_ham_clerk_actor)])
async def post_social_policy_rollback(
    body: RollbackRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> dict[str, Any]:
    ham_bearer = resolve_ham_operator_authorization_header(
        authorization=authorization,
        x_ham_operator_authorization=x_ham_operator_authorization,
    )
    _require_policy_write_token(ham_bearer)
    _require_rollback_phrase(body.confirmation_phrase)
    root = _project_root()
    try:
        result: RollbackResult = rollback_social_policy(root, body.backup_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_BACKUP_NOT_FOUND",
                    "message": str(exc),
                }
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "SOCIAL_POLICY_ROLLBACK_INVALID",
                    "message": str(exc),
                }
            },
        ) from exc
    return {
        "project_root": str(root.resolve()),
        "pre_rollback_backup_id": result.backup_id,
        "audit_id": result.audit_id,
        "effective_after": result.effective_after,
        "new_revision": result.new_revision,
    }


@router.get("/history", dependencies=[Depends(get_ham_clerk_actor)])
async def get_social_policy_history() -> dict[str, Any]:
    root = _project_root()
    return {
        "project_root": str(root.resolve()),
        "backups": list_backups(root),
        "read_only": True,
    }


@router.get("/audit", dependencies=[Depends(get_ham_clerk_actor)])
async def get_social_policy_audit() -> dict[str, Any]:
    root = _project_root()
    return {
        "project_root": str(root.resolve()),
        "audits": list_audit_envelopes(root),
        "read_only": True,
    }
