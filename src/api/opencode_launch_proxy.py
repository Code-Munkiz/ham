"""Chat-origin OpenCode launch proxy — ``POST /api/opencode/build/launch_proxy``.

This route is the browser-callable side of the OpenCode managed-workspace
build lane. The operator route at ``POST /api/opencode/build/launch`` still
requires a ``HAM_OPENCODE_EXEC_TOKEN`` value to be presented over the wire
(``Authorization: Bearer …``); that path is meant for trusted operator /
CLI callers that already hold the exec token.

The chat-side ``CodingPlanCard`` cannot present such a token without
embedding it in the browser, which would defeat the purpose of the token
gate. This proxy lets a Clerk-authenticated browser caller request a
managed-workspace OpenCode build, re-runs the full server-side gate
stack (project lookup, output-target check, build-approver check,
readiness probe, digest verification), reads ``HAM_OPENCODE_EXEC_TOKEN``
**only from the process environment**, and delegates to the same
``_run_opencode_launch_core`` helper that drives the operator route.

Hard rules:

- The exec token value is never reflected to the response body, response
  headers, structured logs, audit JSONL, or any other browser-visible
  surface. The token is read with :func:`os.environ.get` inside the
  handler and never logged.
- The proxy does **not** accept an ``Authorization`` header for the
  OpenCode exec token. ``Authorization: Bearer …`` is consulted by the
  Clerk session dependency for the user's session JWT only; the
  OpenCode exec token comes from process env, never from the request.
- The proxy rejects unknown request body fields via Pydantic's
  ``extra="forbid"`` so a misbehaving client cannot smuggle alternate
  token fields (``exec_token``, ``token``, ``authorization`` …) past
  the gate.

The shape of the response is identical to the operator route so existing
UI/test helpers can consume both surfaces uniformly.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.api.droid_build import _require_build_approver
from src.api.opencode_build import (
    HOSTED_CLOUD_RUN_DEFAULT_HTTP_DEADLINE_S,
    OPENCODE_REGISTRY_REVISION,
    _run_opencode_launch_core,
    _truthy_env,
    effective_opencode_launch_deadline_s,
    verify_opencode_launch_against_preview,
)
from src.ham.clerk_auth import HamActor
from src.ham.coding_router.opencode_provider import (
    OPENCODE_EXECUTION_ENABLED_ENV_NAME,
)
from src.ham.worker_adapters.opencode_adapter import (
    OPENCODE_ENABLED_ENV_NAME,
    OpenCodeStatus,
    check_opencode_readiness,
)
from src.persistence.project_store import get_project_store
from src.persistence.workspace_store import WorkspaceStore

_LOG = logging.getLogger(__name__)

_OPENCODE_EXEC_TOKEN_ENV = "HAM_OPENCODE_EXEC_TOKEN"  # noqa: S105


router = APIRouter(
    prefix="/api/opencode/build",
    tags=["coding-opencode-proxy"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


class OpencodeLaunchProxyBody(BaseModel):
    """Browser-callable body. Rejects extra keys so a misbehaving caller
    cannot smuggle a token field past the gate."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)
    model: str | None = Field(default=None, max_length=180)
    proposal_digest: str = Field(min_length=64, max_length=64)
    base_revision: str = Field(min_length=1, max_length=64)
    confirmed: bool = False


def _require_proxy_opencode_enabled() -> None:
    if not _truthy_env(OPENCODE_ENABLED_ENV_NAME):
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_DISABLED",
                    "message": "OpenCode live execution is disabled on this host.",
                }
            },
        )


def _require_proxy_opencode_execution_enabled() -> None:
    if not _truthy_env(OPENCODE_EXECUTION_ENABLED_ENV_NAME):
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_EXECUTION_DISABLED",
                    "message": "OpenCode live execution is not enabled on this host.",
                }
            },
        )


def _require_proxy_project(project_id: str) -> Any:
    pid = (project_id or "").strip()
    rec = get_project_store().get_project(pid)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "PROJECT_NOT_FOUND",
                    "message": f"Unknown project_id {pid!r}.",
                }
            },
        )
    if not getattr(rec, "build_lane_enabled", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "BUILD_LANE_NOT_ENABLED_FOR_PROJECT",
                    "message": "Build lane is not enabled for this project.",
                }
            },
        )
    return rec


def _require_proxy_managed_workspace_target(rec: Any) -> None:
    target = (getattr(rec, "output_target", None) or "managed_workspace").strip()
    if target != "managed_workspace":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "OUTPUT_TARGET_REQUIRED_MANAGED_WORKSPACE",
                    "message": ("OpenCode chat launches only target managed-workspace projects."),
                }
            },
        )


def _require_proxy_readiness(actor: HamActor | None) -> None:
    readiness = check_opencode_readiness(actor)
    if readiness.status != OpenCodeStatus.CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_LANE_UNCONFIGURED",
                    "message": (
                        "The OpenCode build lane is not configured on this host yet. "
                        "Contact your workspace operator."
                    ),
                }
            },
        )


def _require_proxy_env_token() -> None:
    """Verify the exec token is configured in the process environment.

    The token value is consulted only here and never returned, logged, or
    surfaced to the browser. We assert presence; we do not echo any part
    of the value into the response or into the structured log.
    """
    if not (os.environ.get(_OPENCODE_EXEC_TOKEN_ENV) or "").strip():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "OPENCODE_LANE_UNCONFIGURED",
                    "message": (
                        "The OpenCode build lane is not configured on this host yet. "
                        "Contact your workspace operator."
                    ),
                }
            },
        )


@router.post("/launch_proxy")
async def launch_opencode_build_proxy(
    body: OpencodeLaunchProxyBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    workspace_store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Browser-callable OpenCode launch with token-free request shape."""
    if not body.confirmed:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "NOT_APPROVED",
                    "message": "Approve the build before sending.",
                }
            },
        )

    _require_proxy_opencode_enabled()
    _require_proxy_opencode_execution_enabled()
    rec = _require_proxy_project(body.project_id)
    _require_proxy_managed_workspace_target(rec)
    _require_build_approver(ham_actor, rec, workspace_store)
    _require_proxy_readiness(ham_actor)

    v_err = verify_opencode_launch_against_preview(
        project_id=rec.id,
        user_prompt=body.user_prompt,
        model=body.model,
        proposal_digest=body.proposal_digest,
        base_revision=body.base_revision,
    )
    if v_err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "OPENCODE_LAUNCH_PREVIEW_STALE",
                    "message": v_err,
                }
            },
        )

    _require_proxy_env_token()

    deadline_s = effective_opencode_launch_deadline_s()
    _LOG.info(
        "opencode_launch_proxy.launch_proxy_started project_id=%s launch_deadline_seconds=%s launch_timeout_before_cloud_run_deadline=%s",
        rec.id,
        deadline_s,
        deadline_s < HOSTED_CLOUD_RUN_DEFAULT_HTTP_DEADLINE_S,
    )
    _LOG.info(
        "opencode_launch_proxy.launch_thread_started project_id=%s",
        rec.id,
    )

    return await asyncio.to_thread(
        _run_opencode_launch_core,
        rec=rec,
        ham_actor=ham_actor,
        user_prompt=body.user_prompt,
        model=body.model,
        proposal_digest=body.proposal_digest,
    )


__all__ = [
    "OPENCODE_REGISTRY_REVISION",
    "OpencodeLaunchProxyBody",
    "router",
]
