"""
Gated Factory Droid Build router — POST /api/droid/build/preview + /launch.

This router is the **mutating** counterpart to ``src/api/droid_audit.py``. The
audit router exposes only the read-only ``readonly_repo_audit`` workflow and
must remain untouched. This router exposes only the ``safe_edit_low`` workflow
and is hardcoded server-side; the workflow id is **never** read from the
client request and is **never** echoed in user-facing response fields. The
internal workflow id, ``--auto low`` flag, argv, and the
``HAM_DROID_EXEC_TOKEN`` env name are deliberately kept out of the response
shape.

Fail-closed gates (in the order checked):

1. Clerk session required (router-level dep).
2. Project must exist and have ``build_lane_enabled=True``.
3. Project's ``output_target``-specific required fields:
   * ``github_pr`` → ``github_repo`` configured.
   * ``managed_workspace`` → ``workspace_id`` assigned.
4. Target-aware build approver:
   * ``github_pr`` → caller must be a workspace operator
     (``actor_is_workspace_operator`` against ``HAM_WORKSPACE_OPERATOR_EMAILS``).
   * ``managed_workspace`` → caller must be the workspace ``owner`` or
     ``admin`` on the project's ``workspace_id`` (resolved through
     :func:`resolve_workspace_context`).
5. Launch must include ``confirmed=True``; ``accept_pr=True`` is required
   only for ``github_pr``.
6. Proposal digest + base revision must match the prior preview.
7. ``HAM_DROID_EXEC_TOKEN`` must be configured on the API host.

If any gate fails, the route returns a structured error and **never** touches
the runner, never spawns ``droid``, never opens a PR, and never writes to the
project store.

The launch executor (``execute_droid_build_workflow``) is a thin seam so
tests can mock the post-Droid commit/push/PR step without invoking real
``git`` / ``gh`` / network calls. The production wiring of that executor
lives in ``src/ham/droid_runner/build_lane.py`` and is intentionally inert
in P3 — it cannot be reached today because ``HAM_DROID_EXEC_TOKEN`` is not
set on any deployed host.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.dependencies.workspace import get_workspace_store
from src.ham.clerk_auth import HamActor
from src.ham.clerk_operator import actor_is_workspace_operator
from src.ham.droid_workflows.preview_launch import (
    build_droid_preview,
    execute_droid_build_workflow_remote,
    verify_launch_against_preview,
)
from src.ham.droid_workflows.registry import REGISTRY_REVISION, get_workflow
from src.ham.workspace_resolver import (
    WorkspaceForbidden,
    WorkspaceNotFound,
    resolve_workspace_context,
)
from src.persistence.control_plane_run import DroidBuildOutcome
from src.persistence.project_store import get_project_store
from src.persistence.workspace_store import WorkspaceStore

# Hardcoded server-side. NEVER read from the client. NEVER echoed in a response field.
_BUILD_WORKFLOW_ID = "safe_edit_low"

# Token gate — must be configured on the API host before any launch executes.
# This is the *name* of an env var, not a secret value (S105 false positive).
_DROID_EXEC_TOKEN_ENV = "HAM_DROID_EXEC_TOKEN"  # noqa: S105


router = APIRouter(
    prefix="/api/droid/build",
    tags=["control-plane"],
    dependencies=[Depends(get_ham_clerk_actor)],
)


# ---------------------------------------------------------------------------
# Internal helpers (all gates fail closed before any executor call).
# ---------------------------------------------------------------------------


def _build_workflow_or_500() -> Any:
    wf = get_workflow(_BUILD_WORKFLOW_ID)
    if wf is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DROID_BUILD_WORKFLOW_MISSING",
                    "message": "The build workflow is not registered on this API host.",
                }
            },
        )
    if not wf.mutates or not wf.requires_launch_token:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "DROID_BUILD_WORKFLOW_MISCONFIGURED",
                    "message": "The build workflow has been misconfigured (mutation/token flags).",
                }
            },
        )
    return wf


def _require_workspace_operator(actor: HamActor | None) -> None:
    if not actor_is_workspace_operator(actor):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "WORKSPACE_OPERATOR_REQUIRED",
                    "message": "This action requires a workspace operator.",
                }
            },
        )


_BUILD_APPROVER_ROLES: frozenset[str] = frozenset({"owner", "admin"})


def _require_build_approver(
    actor: HamActor | None,
    rec: Any,
    store: WorkspaceStore,
) -> None:
    """Target-aware build approval gate.

    - ``output_target == "github_pr"`` keeps the strict global gate
      (``actor_is_workspace_operator`` against ``HAM_WORKSPACE_OPERATOR_EMAILS``).
      Opening a real PR still requires a deployment-wide operator.
    - ``output_target == "managed_workspace"`` instead requires a
      Clerk-authenticated caller whose workspace role on the project's
      ``workspace_id`` is ``owner`` or ``admin``. Members and viewers
      cannot approve managed builds; the global operator allowlist is
      not consulted on this path.

    Fails closed with structured 403 / 422 codes that never echo the
    operator allowlist, token env names, or runner URLs.
    """
    target = (getattr(rec, "output_target", None) or "managed_workspace").strip()
    if target == "github_pr":
        _require_workspace_operator(actor)
        return
    if target != "managed_workspace":
        # Defensive: unknown target — refuse rather than silently fall through.
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "BUILD_LANE_PROJECT_UNSUPPORTED_OUTPUT_TARGET",
                    "message": "This project has an unsupported build output target.",
                }
            },
        )
    if actor is None or not (actor.user_id or "").strip():
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "CLERK_SESSION_REQUIRED",
                    "message": "Sign in to approve a managed workspace build.",
                }
            },
        )
    workspace_id = (getattr(rec, "workspace_id", None) or "").strip()
    if not workspace_id:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "BUILD_LANE_PROJECT_MISSING_WORKSPACE_ID",
                    "message": (
                        "This project is configured for managed workspace builds "
                        "but has no workspace assigned yet."
                    ),
                }
            },
        )
    try:
        ctx = resolve_workspace_context(actor, workspace_id, store)
    except WorkspaceNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "WORKSPACE_NOT_FOUND",
                    "message": str(exc) or "Workspace not found.",
                }
            },
        ) from exc
    except WorkspaceForbidden as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "HAM_PERMISSION_DENIED",
                    "message": str(exc) or "You do not have access to this workspace.",
                }
            },
        ) from exc
    if (ctx.role or "").strip().lower() not in _BUILD_APPROVER_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "HAM_PERMISSION_DENIED",
                    "message": (
                        "Only a workspace owner or admin can approve a managed "
                        "workspace build."
                    ),
                }
            },
        )


def _require_build_lane_project(project_id: str) -> Any:
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
    # ``github_repo`` is only meaningful (and only required) for the github_pr
    # output target. Managed-workspace projects intentionally have no GitHub repo;
    # their post-exec path snapshots the runner working tree instead of opening PRs.
    target = (getattr(rec, "output_target", None) or "managed_workspace").strip()
    if target == "github_pr":
        repo = (getattr(rec, "github_repo", None) or "").strip()
        if not repo:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "BUILD_LANE_PROJECT_MISSING_GITHUB_REPO",
                        "message": (
                            "Project uses output_target=github_pr but has no github_repo "
                            "configured."
                        ),
                    }
                },
            )
    return rec


def _require_droid_exec_token() -> None:
    if not (os.environ.get(_DROID_EXEC_TOKEN_ENV) or "").strip():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "BUILD_LANE_UNCONFIGURED",
                    "message": (
                        "The Factory Droid build lane is not configured on this host yet. "
                        "Try the read-only audit lane or contact your workspace operator."
                    ),
                }
            },
        )


def _created_by(actor: HamActor | None) -> dict[str, Any] | None:
    if actor is None:
        return None
    d: dict[str, Any] = {"user_id": actor.user_id}
    if actor.org_id:
        d["org_id"] = actor.org_id
    if actor.email:
        d["email"] = actor.email
    if actor.session_id:
        d["session_id"] = actor.session_id
    return d


# ---------------------------------------------------------------------------
# Launch executor seam (mocked in tests; inert in P3 production).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DroidBuildLaunchOutcome:
    """In-router shape returned by :func:`execute_droid_build_workflow`.

    ``output_target`` and ``output_ref`` are the target-neutral fields
    introduced in PR-A. The legacy ``pr_*`` and ``build_outcome`` fields
    are populated only for ``output_target == "github_pr"`` runs and are
    retained for backward compatibility.
    """

    ok: bool
    ham_run_id: str | None
    control_plane_status: str | None
    pr_url: str | None
    pr_branch: str | None
    pr_commit_sha: str | None
    build_outcome: DroidBuildOutcome | None
    summary: str | None
    error_summary: str | None
    output_target: str | None = None
    output_ref: dict[str, Any] | None = None


def execute_droid_build_workflow(
    *,
    project_id: str,
    project_root: Path,
    user_prompt: str,
    proposal_digest: str,
    created_by: dict[str, Any] | None,
    output_target: str = "github_pr",
    workspace_id: str | None = None,
) -> DroidBuildLaunchOutcome:
    """
    Drive the safe_edit_low workflow plus the runner-side Build Lane post-exec.

    This function is a deliberate seam: tests patch it directly and assert that
    the gate stack runs *before* it is reached. Production cannot reach it
    today because :func:`_require_droid_exec_token` fails closed unless an
    operator sets ``HAM_DROID_EXEC_TOKEN`` on the API host AND the deployed
    runner exposes the Build Lane post-exec step.

    The runner is the authority on branch/commit/PR text. This API hands the
    runner the workflow id, project id, project root, sanitized prompt, and
    proposal digest; the runner sanitizes its own output, runs ``git`` and
    ``gh pr create`` under ``shell=False``, refuses sensitive-path changes,
    refuses to push the base branch, and returns the PR coordinates.
    """
    launch = execute_droid_build_workflow_remote(
        workflow_id=_BUILD_WORKFLOW_ID,
        project_root=project_root,
        user_prompt=user_prompt,
        project_id=project_id,
        proposal_digest=proposal_digest,
        created_by=created_by,
        output_target=output_target,
        workspace_id=workspace_id,
    )
    return DroidBuildLaunchOutcome(
        ok=launch.ok,
        ham_run_id=launch.ham_run_id,
        control_plane_status=launch.control_plane_status,
        pr_url=launch.pr_url,
        pr_branch=launch.pr_branch,
        pr_commit_sha=launch.pr_commit_sha,
        build_outcome=launch.build_outcome,
        summary=launch.summary,
        error_summary=launch.build_error_summary or launch.blocking_reason,
        output_target=launch.output_target,
        output_ref=launch.output_ref,
    )


# ---------------------------------------------------------------------------
# Pydantic bodies — both reject extra fields. ``workflow_id`` is never accepted.
# ---------------------------------------------------------------------------


class DroidBuildPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)


class DroidBuildLaunchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=180)
    user_prompt: str = Field(min_length=1, max_length=12_000)
    proposal_digest: str = Field(min_length=64, max_length=64)
    base_revision: str = Field(min_length=1, max_length=64)
    confirmed: bool = False
    accept_pr: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _user_facing_summary(output_target: str) -> str:
    """Sanitized preview summary — never exposes workflow id, argv, or token env."""
    target = (output_target or "").strip()
    if target == "managed_workspace":
        return (
            "This action proposes a low-risk managed workspace snapshot: "
            "documentation, comments, and non-behavioral edits only. "
            "HAM will capture a preview snapshot for you to review before "
            "anything is published. No CI configuration or business logic "
            "will be modified."
        )
    return (
        "This action proposes a low-risk pull request: documentation, comments, "
        "and non-behavioral edits only. You will review and approve the PR on "
        "GitHub before anything merges. No CI configuration or business logic "
        "will be modified."
    )


@router.post("/preview")
async def preview_droid_build(
    body: DroidBuildPreviewBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    workspace_store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Preview a build (low-risk PR-opening) workflow. No execution; returns a digest."""
    _build_workflow_or_500()
    rec = _require_build_lane_project(body.project_id)
    _require_build_approver(ham_actor, rec, workspace_store)
    prev = build_droid_preview(
        workflow_id=_BUILD_WORKFLOW_ID,
        project_id=rec.id,
        project_root=Path(rec.root),
        user_prompt=body.user_prompt,
    )
    if not prev.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DROID_BUILD_PREVIEW_BLOCKED",
                    "message": prev.blocking_reason or "Preview blocked.",
                }
            },
        )
    project_output_target = (
        getattr(rec, "output_target", None) or "managed_workspace"
    )
    will_open_pr = project_output_target == "github_pr"
    return {
        "kind": "droid_build_preview",
        "project_id": rec.id,
        "project_name": rec.name,
        "user_prompt": prev.user_prompt,
        "summary": _user_facing_summary(project_output_target),
        "proposal_digest": prev.proposal_digest,
        "base_revision": prev.base_revision,
        "is_readonly": False,
        "will_open_pull_request": will_open_pr,
        "requires_approval": True,
        "output_target": project_output_target,
    }


@router.post("/launch")
async def launch_droid_build(
    body: DroidBuildLaunchBody,
    ham_actor: Annotated[HamActor | None, Depends(get_ham_clerk_actor)],
    workspace_store: Annotated[WorkspaceStore, Depends(get_workspace_store)],
) -> dict[str, Any]:
    """Launch the previewed build. Digest-verified; gated by token + accept_pr + confirmed."""
    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DROID_BUILD_LAUNCH_REQUIRES_CONFIRMATION",
                    "message": "Approve the launch before sending.",
                }
            },
        )
    _build_workflow_or_500()
    rec = _require_build_lane_project(body.project_id)
    _require_build_approver(ham_actor, rec, workspace_store)
    project_output_target = (
        getattr(rec, "output_target", None) or "managed_workspace"
    )
    # ``accept_pr`` is required only when the project's output target opens
    # a real PR. Managed-workspace projects do not open a PR (PR-A: stub;
    # PR-B: snapshot); PR-B will introduce its own ``accept_snapshot``
    # confirmation as appropriate.
    if project_output_target == "github_pr" and not body.accept_pr:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "DROID_BUILD_LAUNCH_REQUIRES_ACCEPT_PR",
                    "message": "Acknowledge that this opens a pull request before sending.",
                }
            },
        )
    root = Path(rec.root)
    v_err = verify_launch_against_preview(
        workflow_id=_BUILD_WORKFLOW_ID,
        project_id=rec.id,
        project_root=root,
        user_prompt=body.user_prompt,
        proposal_digest=body.proposal_digest,
        base_revision=body.base_revision,
    )
    if v_err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "DROID_BUILD_LAUNCH_PREVIEW_STALE",
                    "message": v_err,
                }
            },
        )
    # Token gate is the LAST check: only after every other gate passes do we even
    # consider whether the runner is reachable. This keeps the failure mode honest
    # for non-operators / disabled projects (403 / 422) instead of leaking the
    # token-configured / not-configured signal to unauthorized callers.
    _require_droid_exec_token()

    out = execute_droid_build_workflow(
        project_id=rec.id,
        project_root=root,
        user_prompt=body.user_prompt,
        proposal_digest=body.proposal_digest,
        created_by=_created_by(ham_actor),
        output_target=project_output_target,
        workspace_id=getattr(rec, "workspace_id", None),
    )
    return {
        "kind": "droid_build_launch",
        "project_id": rec.id,
        "ok": out.ok,
        "ham_run_id": out.ham_run_id,
        "control_plane_status": out.control_plane_status,
        "pr_url": out.pr_url,
        "pr_branch": out.pr_branch,
        "pr_commit_sha": out.pr_commit_sha,
        "build_outcome": out.build_outcome,
        "summary": out.summary,
        "error_summary": out.error_summary if not out.ok else None,
        "is_readonly": False,
        "will_open_pull_request": project_output_target == "github_pr",
        "requires_approval": True,
        "output_target": out.output_target or project_output_target,
        "output_ref": out.output_ref,
    }


__all__ = [
    "DroidBuildLaunchOutcome",
    "REGISTRY_REVISION",
    "execute_droid_build_workflow",
    "router",
]
