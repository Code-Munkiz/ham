"""
Clerk identity for HAM (session JWT verification only in this slice).

- Identity: who is calling (user id, org, permissions derived from JWT claims).
- Not an audit store; not a provider credential vault.

Env:
- ``HAM_CLERK_REQUIRE_AUTH``: when ``true``, operator turns require a valid Clerk session JWT.
- ``HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS``: when ``true``, chat entrypoints require a Clerk session
  and (if configured) an allowlisted email/domain — see ``src/ham/clerk_email_access.py``.
- ``CLERK_JWT_ISSUER``: issuer URL, e.g. ``https://YOUR_INSTANCE.clerk.accounts.dev`` (no trailing slash).
- Optional ``CLERK_JWT_AUDIENCE``: set if your Clerk JWT template sets ``aud`` and you want strict verification.

HAM operator tokens (``HAM_*_TOKEN``) must be sent on ``X-Ham-Operator-Authorization: Bearer …``
when ``Authorization`` carries the Clerk session (``HAM_CLERK_REQUIRE_AUTH`` or email enforcement).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from fastapi import HTTPException

# --- Future M2M seam (not wired into enforcement in this slice) -------------------------------


def clerk_m2m_note() -> str:
    """Design hook: later verify Clerk M2M tokens for runner/service callers."""
    return (
        "Clerk machine auth (M2M) is not enforced in this slice; keep using "
        "HAM_DROID_RUNNER_SERVICE_TOKEN / HAM_CURSOR_AGENT_LAUNCH_TOKEN for those paths."
    )


# ----------------------------------------------------------------------------------------------


_EMPTY_WORKSPACES_CLAIM: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class HamActor:
    """Authenticated principal for operator attribution and authz."""

    user_id: str
    org_id: str | None
    session_id: str | None
    email: str | None  # normalized lower-case from JWT ``email`` when present
    permissions: frozenset[str]
    org_role: str | None
    raw_permission_claim: str | None  # evaluation hint for audit (e.g. claim source)
    # Optional ``workspaces`` custom JWT claim of shape ``{wid: role|[perms]}``.
    # Default is an empty read-only mapping for back-compat with existing callers
    # that construct ``HamActor`` positionally without this field.
    # Consumed by :mod:`src.ham.workspace_resolver` to *augment* (never grant)
    # workspace permissions; it cannot bypass Firestore membership.
    workspaces_claim: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_WORKSPACES_CLAIM)


def clerk_operator_require_auth_enabled() -> bool:
    raw = (os.environ.get("HAM_CLERK_REQUIRE_AUTH") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def clerk_email_enforcement_enabled() -> bool:
    raw = (os.environ.get("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def clerk_authorization_is_clerk_session() -> bool:
    """When true, ``Authorization`` is the Clerk JWT; HAM secrets use ``X-Ham-Operator-Authorization``."""
    return clerk_operator_require_auth_enabled() or clerk_email_enforcement_enabled()


def clerk_issuer() -> str:
    return (os.environ.get("CLERK_JWT_ISSUER") or "").strip().rstrip("/")


def extract_workspaces_claim(payload: dict[str, Any]) -> Mapping[str, Any]:
    """Read optional ``workspaces`` custom claim. Always returns a mapping.

    Shape (advisory; resolver authoritative): ``{workspace_id: role_str | [perm,…]}``.
    Non-mapping values are ignored. Empty mapping is the back-compat default.

    Phase 1a only: Phase 1b's resolver consumes this to *augment* — never grant —
    workspace permissions. Membership remains Firestore-backed.
    """
    raw = payload.get("workspaces")
    if not isinstance(raw, dict):
        return _EMPTY_WORKSPACES_CLAIM
    cleaned: dict[str, Any] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if isinstance(v, (str, list, tuple)):
            cleaned[k] = v
    return MappingProxyType(cleaned) if cleaned else _EMPTY_WORKSPACES_CLAIM


def _extract_permissions_and_role(
    payload: dict[str, Any],
) -> tuple[frozenset[str], str | None, str | None]:
    """
    Build effective permissions from JWT claims.

    Supports:
    - ``permissions`` list (Clerk custom permissions in JWT template).
    - ``org_permissions`` alternate key.
    - Fallback: map ``org_role`` (e.g. ``org:admin``, ``org:member``).
    """
    perms: set[str] = set()
    src: str | None = None
    raw_list = payload.get("permissions")
    if isinstance(raw_list, list):
        perms.update(str(x) for x in raw_list if x)
        src = "permissions"
    alt = payload.get("org_permissions")
    if isinstance(alt, list):
        perms.update(str(x) for x in alt if x)
        src = src or "org_permissions"

    org_role = payload.get("org_role")
    if org_role is None:
        org_role = payload.get("role")
    role_str = str(org_role) if org_role is not None else None

    ORG_ROLE_DEFAULTS: dict[str, frozenset[str]] = {
        "org:admin": frozenset({"ham:admin", "ham:launch", "ham:preview", "ham:status"}),
        "org:member": frozenset({"ham:preview", "ham:status"}),
    }
    if role_str and role_str in ORG_ROLE_DEFAULTS:
        perms |= set(ORG_ROLE_DEFAULTS[role_str])
        src = src or "org_role_fallback"

    if "ham:admin" in perms:
        perms |= {"ham:launch", "ham:preview", "ham:status"}

    return frozenset(perms), role_str, src


def verify_clerk_session_jwt(token: str) -> HamActor:
    """Verify Clerk session JWT via JWKS; raise HTTPException on failure."""
    issuer = clerk_issuer()
    if not issuer:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "CLERK_MISCONFIGURED",
                    "message": "CLERK_JWT_ISSUER is not set on the API host.",
                }
            },
        )
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "CLERK_DEPS_MISSING",
                    "message": "Install PyJWT for Clerk verification (pip install PyJWT cryptography).",
                }
            },
        ) from exc

    jwks_url = f"{issuer}/.well-known/jwks.json"
    try:
        jwks_client = PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        audience = (os.environ.get("CLERK_JWT_AUDIENCE") or "").strip() or None
        if audience:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                issuer=issuer,
                audience=audience,
            )
        else:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                issuer=issuer,
                options={"verify_aud": False},
            )
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "CLERK_SESSION_INVALID",
                    "message": f"Invalid Clerk session: {exc}",
                }
            },
        ) from exc

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "CLERK_SESSION_INVALID", "message": "Token missing sub"}},
        )
    org_id = payload.get("org_id")
    if org_id is not None:
        org_id = str(org_id)
    sid = payload.get("sid")
    if sid is not None:
        sid = str(sid)
    perms, org_role, src = _extract_permissions_and_role(payload)
    email_raw = payload.get("email")
    email_norm: str | None
    if email_raw is None or email_raw == "":
        email_norm = None
    else:
        email_norm = str(email_raw).strip().lower() or None
    return HamActor(
        user_id=str(sub),
        org_id=org_id,
        session_id=sid,
        email=email_norm,
        permissions=perms,
        org_role=org_role,
        raw_permission_claim=src,
        workspaces_claim=extract_workspaces_claim(payload),
    )


def resolve_ham_operator_authorization_header(
    *,
    authorization: str | None,
    x_ham_operator_authorization: str | None,
) -> str | None:
    """
    Header used by ``_require_bearer`` for HAM launch/settings/droid exec tokens.

    When Clerk is required for operator, HAM tokens must use ``X-Ham-Operator-Authorization``.
    Otherwise ``Authorization`` is used (legacy single-header deployments).
    """
    xham = (x_ham_operator_authorization or "").strip()
    if xham:
        return xham
    if clerk_authorization_is_clerk_session():
        return None
    auth = (authorization or "").strip()
    return auth or None


def actor_attribution_dict(actor: HamActor | None) -> dict[str, Any]:
    if actor is None:
        return {
            "clerk_user_id": None,
            "clerk_org_id": None,
            "clerk_session_id": None,
            "clerk_email": None,
            "ham_permissions_effective": None,
            "clerk_org_role": None,
            "permission_claim_source": None,
        }
    return {
        "clerk_user_id": actor.user_id,
        "clerk_org_id": actor.org_id,
        "clerk_session_id": actor.session_id,
        "clerk_email": actor.email,
        "ham_permissions_effective": sorted(actor.permissions),
        "clerk_org_role": actor.org_role,
        "permission_claim_source": actor.raw_permission_claim,
    }
