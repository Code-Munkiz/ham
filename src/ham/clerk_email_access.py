"""
HAM defense-in-depth: restrict Clerk-authenticated chat access by email / domain.

Clerk Dashboard **Restricted mode** and **Allowlist** remain the primary app-wide gate;
this module enforces a second line when ``HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS`` is enabled.

Env:
- ``HAM_CLERK_ALLOWED_EMAILS`` — comma-separated exact emails (case-insensitive).
- ``HAM_CLERK_ALLOWED_EMAIL_DOMAINS`` — comma-separated domains, e.g. ``company.com`` (case-insensitive).
- ``HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS`` — when true, chat entrypoints require a verified session
  and an email that matches at least one allowlist entry.

When enforcement is on and **both** allowlists parse to empty → **fail closed** (deny all).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

from src.ham.clerk_auth import HamActor, clerk_email_enforcement_enabled
from src.ham.operator_audit import append_operator_action_audit


def _parse_email_allowlist(raw: str) -> set[str]:
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _parse_domain_allowlist(raw: str) -> set[str]:
    out: set[str] = set()
    for x in raw.split(","):
        s = x.strip().lower()
        if not s:
            continue
        out.add(s.lstrip("@"))
    return out


def ham_clerk_allowed_emails_config() -> set[str]:
    return _parse_email_allowlist(os.environ.get("HAM_CLERK_ALLOWED_EMAILS", ""))


def ham_clerk_allowed_domains_config() -> set[str]:
    return _parse_domain_allowlist(os.environ.get("HAM_CLERK_ALLOWED_EMAIL_DOMAINS", ""))


def evaluate_ham_clerk_email_denial_reason(actor: HamActor) -> str | None:
    """
    Returns ``None`` if the actor is allowed; otherwise a stable denial reason code
    (``no_allowlist_configured``, ``missing_email_claim``, ``disallowed_email_or_domain``).
    """
    emails = ham_clerk_allowed_emails_config()
    domains = ham_clerk_allowed_domains_config()
    if not emails and not domains:
        return "no_allowlist_configured"

    addr = (actor.email or "").strip().lower()
    if not addr:
        return "missing_email_claim"

    if addr in emails:
        return None
    if "@" in addr:
        dom = addr.rsplit("@", 1)[-1]
        if dom in domains:
            return None
    return "disallowed_email_or_domain"


def require_ham_clerk_email_allowed(actor: HamActor, *, route: str) -> None:
    """Raise ``HTTPException`` 403 after optional HAM audit when enforcement is on and identity fails."""
    if not clerk_email_enforcement_enabled():
        return
    reason = evaluate_ham_clerk_email_denial_reason(actor)
    if reason is None:
        return

    row: dict[str, Any] = {
        "event": "ham_access_denied",
        "denial_reason": reason,
        "evaluated_email": actor.email.strip().lower() if actor.email else None,
        "clerk_user_id": actor.user_id,
        "clerk_org_id": actor.org_id,
        "clerk_session_id": actor.session_id,
        "route": route,
        "audit_sink": "ham_local_jsonl",
    }
    append_operator_action_audit(row)

    raise HTTPException(
        status_code=403,
        detail={
            "error": {
                "code": "HAM_EMAIL_RESTRICTION",
                "message": (
                    "Access to this Ham deployment is restricted by email or domain. "
                    "Your signed-in account is not allowed, or the session has no email claim."
                ),
                "denial_reason": reason,
            }
        },
    )
