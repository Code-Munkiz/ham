"""Social autonomy scheduler-callable tick route.

POST /api/social/autonomy/scheduled-tick

Disabled by default — when ``HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED != "true"``,
returns 503 with structured ``AUTONOMY_SCHEDULER_DISABLED`` error.

Auth chain (fail-closed at every layer):

1. OIDC verification preferred, mirroring ``src/api/internal_dispatcher.py``'s
   ``_validate_oidc_token`` — ``HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT``
   allowlist + ``HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE`` audience claim.
2. Bearer fallback via ``HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN`` shared secret,
   mirroring ``_require_social_live_token``.
   Missing/invalid → 401.

Dry-run interlock (defaults ``dry_run=True``):
  Hard-rejects ``dry_run=False`` from this endpoint UNLESS triple env interlock
  is present: ``_ENABLED=true`` + ``_DRY_RUN=false`` + ``HAM_SOCIAL_LIVE_APPLY_TOKEN``
  set.

Delegates to ``run_social_autonomy_tick(dry_run=resolved, run_once=True,
actor="social-autonomy-scheduled-tick")`` — no new business logic.

Updates the M1 scheduler-state store with ``last_scheduled_tick_at`` +
``last_tick_summary`` snapshot on each invocation.
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from src.ham.social_scheduler_state_store import (
    get_social_scheduler_state_store,
)

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api/social", tags=["social"])

# Environment variable names
_ENABLED_ENV = "HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED"
_SA_ENV = "HAM_SOCIAL_AUTONOMY_SCHEDULER_SERVICE_ACCOUNT"
_AUDIENCE_ENV = "HAM_SOCIAL_AUTONOMY_SCHEDULER_AUDIENCE"
_BEARER_TOKEN_ENV = "HAM_SOCIAL_AUTONOMY_SCHEDULER_TOKEN"  # noqa: S105
_DRY_RUN_ENV = "HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN"
_LIVE_APPLY_TOKEN_ENV = "HAM_SOCIAL_LIVE_APPLY_TOKEN"  # noqa: S105

# Distinguishing actor for audit envelopes (differs from Clerk-gated route)
_ACTOR = "social-autonomy-scheduled-tick"


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class ScheduledTickRequest(BaseModel):
    """Request body for the scheduler-callable tick route."""

    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scheduler_enabled() -> bool:
    """Return True only when HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED=true."""
    return (os.environ.get(_ENABLED_ENV) or "").strip().lower() == "true"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _project_root() -> Path:
    return Path.cwd()


def _resolve_bearer_header(
    authorization: str | None,
    x_ham_operator_authorization: str | None,
) -> str | None:
    """Resolve the raw bearer header value.

    ``X-Ham-Operator-Authorization`` is preferred when present, matching
    the pattern in ``src/ham/clerk_auth.resolve_ham_operator_authorization_header``.
    """
    xham = (x_ham_operator_authorization or "").strip()
    if xham:
        return xham
    auth = (authorization or "").strip()
    return auth or None


def _extract_token(raw_header: str) -> str:
    """Strip the 'Bearer ' prefix if present."""
    if raw_header.lower().startswith("bearer "):
        return raw_header[7:].strip()
    return raw_header.strip()


# ---------------------------------------------------------------------------
# OIDC verification (mirrors internal_dispatcher._verify_google_oidc_token)
# ---------------------------------------------------------------------------


def _verify_google_oidc_token(token: str, *, expected_aud: str) -> dict[str, Any]:
    """Verify OIDC token signature + standard claims using the Google verifier.

    Raises:
        HTTPException(503) — google-auth runtime unavailable.
        HTTPException(401) — token invalid (signature, issuer, audience, etc.).
    """
    try:
        from google.auth.transport.requests import Request  # noqa: PLC0415
        from google.oauth2 import id_token  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "SCHEDULED_TICK_AUTH_RUNTIME_MISSING",
                    "message": "google-auth runtime is required for OIDC verification.",
                }
            },
        ) from exc

    try:
        payload = id_token.verify_oauth2_token(token, Request(), audience=expected_aud)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SCHEDULED_TICK_TOKEN_INVALID",
                    "message": f"OIDC token verification failed: {exc}",
                }
            },
        ) from exc

    # Defensive issuer allowlist (mirrors internal_dispatcher.py)
    issuer = str(payload.get("iss") or "")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SCHEDULED_TICK_TOKEN_INVALID",
                    "message": "OIDC token issuer is not trusted.",
                }
            },
        )

    # Defensive audience check (real verifier enforces this, but we verify it
    # defensively so mocked verifiers in tests don't bypass the check)
    aud = payload.get("aud")
    if aud != expected_aud:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SCHEDULED_TICK_TOKEN_INVALID",
                    "message": "OIDC token audience does not match expected audience.",
                }
            },
        )

    return payload


# ---------------------------------------------------------------------------
# Auth chain
# ---------------------------------------------------------------------------


def _validate_auth(
    authorization: str | None,
    x_ham_operator_authorization: str | None,
) -> None:
    """Fail-closed auth chain: try OIDC first, then shared bearer.

    Raises HTTPException(401) or HTTPException(503) on failure.
    Returns silently on success.
    """
    expected_sa = (os.environ.get(_SA_ENV) or "").strip()
    expected_aud = (os.environ.get(_AUDIENCE_ENV) or "").strip()
    bearer_secret = (os.environ.get(_BEARER_TOKEN_ENV) or "").strip()

    raw_header = _resolve_bearer_header(authorization, x_ham_operator_authorization)

    if not raw_header:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SCHEDULED_TICK_TOKEN_MISSING",
                    "message": "Authorization: Bearer <token> required.",
                }
            },
        )

    token = _extract_token(raw_header)

    oidc_configured = bool(expected_sa and expected_aud)
    bearer_configured = bool(bearer_secret)

    # ── OIDC path ─────────────────────────────────────────────────────────
    if oidc_configured:
        try:
            payload = _verify_google_oidc_token(token, expected_aud=expected_aud)
        except HTTPException as exc:
            if exc.status_code == 503:
                # google-auth runtime missing — do not attempt bearer fallback
                raise
            if not bearer_configured:
                # OIDC failed and no bearer fallback available
                raise
            # OIDC 401 → fall through to bearer fallback below
        else:
            # OIDC verification succeeded — check email allowlist
            email = str(payload.get("email") or "")
            if email == expected_sa:
                return  # Auth success via OIDC
            # Wrong service account email
            _LOG.warning("OIDC email mismatch: got %r, expected %r", email, expected_sa)
            if not bearer_configured:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": {
                            "code": "SCHEDULED_TICK_TOKEN_INVALID",
                            "message": "OIDC token email does not match the allowlisted service account.",
                        }
                    },
                )
            # Fall through to bearer fallback

    # ── Bearer path ────────────────────────────────────────────────────────
    if bearer_configured:
        if hmac.compare_digest(token.encode("utf-8"), bearer_secret.encode("utf-8")):
            return  # Auth success via bearer
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "SCHEDULED_TICK_TOKEN_INVALID",
                    "message": "Shared bearer token is invalid.",
                }
            },
        )

    # Neither OIDC nor bearer configured → fail
    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "code": "SCHEDULED_TICK_TOKEN_MISSING",
                "message": (
                    "No auth verifier configured. "
                    f"Set {_SA_ENV} + {_AUDIENCE_ENV} (OIDC) "
                    f"or {_BEARER_TOKEN_ENV} (bearer)."
                ),
            }
        },
    )


# ---------------------------------------------------------------------------
# Dry-run interlock
# ---------------------------------------------------------------------------


def _resolve_dry_run(body_dry_run: bool) -> bool:
    """Resolve effective dry_run value against the triple-env interlock.

    Live mode (dry_run=False) is permitted ONLY when ALL THREE of:
    - HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED == "true"
    - HAM_SOCIAL_AUTONOMY_SCHEDULER_DRY_RUN == "false"
    - HAM_SOCIAL_LIVE_APPLY_TOKEN is set (non-empty)

    Any missing or incorrect env forces dry_run=True regardless of body.
    """
    scheduler_enabled = _scheduler_enabled()
    dry_run_env_false = (os.environ.get(_DRY_RUN_ENV) or "").strip().lower() == "false"
    live_apply_token_set = bool((os.environ.get(_LIVE_APPLY_TOKEN_ENV) or "").strip())

    if scheduler_enabled and dry_run_env_false and live_apply_token_set and not body_dry_run:
        return False  # Live mode permitted

    return True  # Default: dry run


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.post("/autonomy/scheduled-tick")
def run_scheduled_tick(
    body: ScheduledTickRequest | None = None,
    authorization: str | None = Header(None, alias="Authorization"),
    x_ham_operator_authorization: str | None = Header(None, alias="X-Ham-Operator-Authorization"),
) -> Any:
    """POST /api/social/autonomy/scheduled-tick — scheduler-callable tick route.

    Disabled by default (HAM_SOCIAL_AUTONOMY_SCHEDULER_ENABLED != "true" → 503).
    Auth chain: OIDC preferred, bearer fallback. Fail-closed at every layer.
    Dry-run interlock: defaults dry_run=True; live mode requires triple env.
    Delegates to run_social_autonomy_tick with actor="social-autonomy-scheduled-tick".
    Updates the scheduler-state store on each invocation.
    """
    # Gate 1: scheduler must be explicitly enabled
    if not _scheduler_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "AUTONOMY_SCHEDULER_DISABLED",
                    "message": (
                        f"Social autonomy scheduler is disabled. Set {_ENABLED_ENV}=true to enable."
                    ),
                }
            },
        )

    # Gate 2: auth (fail-closed — both OIDC and bearer can raise)
    _validate_auth(authorization, x_ham_operator_authorization)

    # Gate 3: dry-run interlock
    req = body or ScheduledTickRequest()
    dry_run = _resolve_dry_run(req.dry_run)

    # Gate 4: delegate to the existing tick runner (no new business logic)
    from src.ham.social_autonomy.tick import run_social_autonomy_tick  # noqa: PLC0415

    result = run_social_autonomy_tick(
        store_path=_project_root(),
        now=_utc_now(),
        dry_run=dry_run,
        run_once=True,
        actor=_ACTOR,
    )

    # Gate 5: update scheduler-state store (best-effort; log on failure)
    try:
        state_store = get_social_scheduler_state_store()
        current = state_store.read_state()
        updated = current.model_copy(
            update={
                "last_scheduled_tick_at": _utc_now(),
                "last_tick_summary": result.model_dump(mode="json"),
            }
        )
        state_store.write_state(updated)
    except Exception:  # noqa: BLE001
        _LOG.exception("scheduled-tick: failed to update scheduler state store after tick")

    return result
