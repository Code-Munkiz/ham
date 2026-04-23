"""
Operator-first deploy **approval policy** for managed Cloud Agent missions (Vercel deploy hook path).

* Default is **off** (no blocking, minimal friction).
* **hard** is the only mode that enforces approval on the server.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.persistence.managed_deploy_approval import ManagedDeployApproval

ManagedDeployApprovalMode = Literal["off", "audit", "soft", "hard"]


def managed_deploy_approval_mode() -> ManagedDeployApprovalMode:
    """
    ``HAM_MANAGED_DEPLOY_APPROVAL_MODE`` — ``off`` | ``audit`` | ``soft`` | ``hard``.

    Default ``off`` (non-blocking). Unknown values fall back to ``off`` to avoid
    surprising operators with accidental enforcement.
    """
    raw = (os.environ.get("HAM_MANAGED_DEPLOY_APPROVAL_MODE") or "").strip().lower()
    if raw in ("off", "audit", "soft", "hard"):
        return raw  # type: ignore[return-value]
    return "off"


def deploy_hook_allowed_in_policy_mode(
    mode: ManagedDeployApprovalMode,
    latest: "ManagedDeployApproval | None",
) -> bool:
    """In ``hard`` only: require latest decision to be **approved** (deny blocks)."""
    if mode != "hard":
        return True
    if latest is None:
        return False
    if latest.state == "denied":
        return False
    return latest.state == "approved"
