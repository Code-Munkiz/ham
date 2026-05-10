"""HAM workspace-operator gate for diagnostic surfaces (e.g. team Cursor key rotate/reveal).

A *workspace operator* is the human (or small team) who provisioned the deployment-global
Cursor team key, configured Cloud Run env, and is responsible for rotating it. Normal
workspace users must NOT see operator-shaped settings details (env names, file paths,
key previews, account email of the operator), or be able to rotate / clear the team key.

Env:
- ``HAM_WORKSPACE_OPERATOR_EMAILS`` — comma-separated exact emails (case-insensitive).
  When set, only these emails are considered workspace operators.

Behaviour matrix (matches existing email allowlist patterns in ``clerk_email_access.py``):

- Clerk auth NOT enforced (local dev, ``HAM_CLERK_REQUIRE_AUTH`` off and email enforcement off):
  any caller is treated as operator. Diagnostic surfaces stay visible during local development.
- Clerk auth enforced and ``HAM_WORKSPACE_OPERATOR_EMAILS`` empty:
  fail-closed — nobody is an operator, the diagnostic drawer + rotate/clear endpoints are
  hidden / 403. Same posture as the email allowlist's "no allowlist configured -> deny".
- Clerk auth enforced and ``HAM_WORKSPACE_OPERATOR_EMAILS`` populated:
  only callers whose JWT ``email`` claim is in the allowlist are operators.

This module never reads or echoes secret values; it only decides ``True`` / ``False``.
"""

from __future__ import annotations

import os

from src.ham.clerk_auth import HamActor, clerk_authorization_is_clerk_session


def workspace_operator_emails_config() -> set[str]:
    raw = os.environ.get("HAM_WORKSPACE_OPERATOR_EMAILS", "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def actor_is_workspace_operator(actor: HamActor | None) -> bool:
    """Return True when ``actor`` may see operator-only diagnostic surfaces.

    See module docstring for the full behaviour matrix. Safe to call for any route
    that previously took ``Depends(get_ham_clerk_actor)``.
    """
    if not clerk_authorization_is_clerk_session():
        return True

    allowlist = workspace_operator_emails_config()
    if not allowlist:
        return False
    if actor is None:
        return False

    email = (actor.email or "").strip().lower()
    if not email:
        return False
    return email in allowlist
