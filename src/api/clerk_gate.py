"""Shared Clerk session + HAM email/domain gate for protected FastAPI routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from src.ham.clerk_auth import (
    HamActor,
    clerk_authorization_is_clerk_session,
    verify_clerk_session_jwt,
)
from src.ham.clerk_email_access import require_ham_clerk_email_allowed


def enforce_clerk_session_and_email_for_request(
    authorization: str | None,
    *,
    route: str,
) -> HamActor | None:
    """
    When ``HAM_CLERK_REQUIRE_AUTH`` or ``HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS`` is on,
    require ``Authorization: Bearer`` Clerk JWT and run email allowlist (if enabled).
    """
    if not clerk_authorization_is_clerk_session():
        return None
    auth = (authorization or "").strip()
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "CLERK_SESSION_REQUIRED",
                    "message": (
                        "Authorization: Bearer <Clerk session JWT> required when "
                        "HAM_CLERK_REQUIRE_AUTH or HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS is enabled. "
                        "Use X-Ham-Operator-Authorization for HAM launch/settings/droid tokens."
                    ),
                }
            },
        )
    actor = verify_clerk_session_jwt(auth[7:].strip())
    require_ham_clerk_email_allowed(actor, route=route)
    return actor


async def get_ham_clerk_actor(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> HamActor | None:
    """FastAPI dependency: same semantics as :func:`enforce_clerk_session_and_email_for_request`."""
    route = f"{request.method} {request.url.path}"
    return enforce_clerk_session_and_email_for_request(authorization, route=route)
