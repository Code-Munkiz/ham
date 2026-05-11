"""Output-target abstraction for the Build Lane post-exec step.

This module introduces a small, target-neutral interface that the runner
service uses after a successful ``droid exec``. Today only the GitHub-PR
adapter has a real implementation; the managed-workspace adapter is a
deliberate stub returning a structured ``MANAGED_WORKSPACE_NOT_IMPLEMENTED``
failure until PR-B lands the snapshot store + GCS upload + diff/preview API.

Why an abstraction at all
-------------------------

The live-beta HAM product is Replit/Manus-shaped: users sign up, create a
workspace, chat with HAM, and HAM builds the app in a managed project
workspace with diff / preview / version history. GitHub is **optional**
connected-repo mode, not the default. The previous Build Lane code path
hard-wired ``git`` and ``gh pr create`` calls into the runner service,
which is correct for connected-repo mode but wrong as a default. This
module lets the runner pick the right adapter per project without any
GitHub host requirements (``gh`` install, GitHub App, repo install) when
``output_target == "managed_workspace"``.

Shape contract
--------------

- :class:`PostExecCommon` carries target-neutral inputs.
- :class:`OutputResult` carries target-neutral outputs plus an opaque,
  target-specific :attr:`OutputResult.target_ref` dict.
- :class:`OutputAdapter` is the Protocol both adapters satisfy.
- :class:`GithubPrAdapter` is the existing GitHub-PR implementation,
  reusing :func:`execute_build_lane_post_exec` under the hood. The
  PR-shaped :class:`src.ham.droid_runner.build_lane.BuildLaneResult` type
  is preserved as the GitHub-PR-specific internal result and lifted into
  the new :class:`OutputResult` shape by :func:`_legacy_to_output_result`.
- :class:`ManagedWorkspaceStubAdapter` is the inert stub. It performs no
  IO, opens no PR, writes no snapshot. It always returns
  ``build_outcome="failed"`` with ``error_summary="MANAGED_WORKSPACE_NOT_IMPLEMENTED"``.

Safety notes
------------

- No subprocess invocations live in this module directly. Both adapters
  rely on the runner-side :data:`SubprocessRunner` seam already exercised
  in tests; the stub never spawns a subprocess.
- No GitHub credential lookup happens here. ``gh`` / git auth lives on
  the runner host and is configured out-of-band.
- ``OutputResult`` is structured and finite — no unbounded strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from src.ham.droid_runner.build_lane import (
    BuildLaneInputs,
    BuildLaneResult,
    SubprocessRunner,
    execute_build_lane_post_exec,
)
from src.persistence.control_plane_run import DroidBuildOutcome

OutputTarget = Literal["managed_workspace", "github_pr"]

# Target-neutral terminal vocabulary. ``GithubPrAdapter`` produces values
# in :data:`DroidBuildOutcome` and lifts them into this neutral vocabulary
# via :func:`_lift_legacy_build_outcome`.
BuildOutcome = Literal[
    "succeeded",
    "nothing_to_change",
    "blocked",
    "failed",
]

BUILD_OUTCOMES: tuple[str, ...] = (
    "succeeded",
    "nothing_to_change",
    "blocked",
    "failed",
)

MANAGED_WORKSPACE_NOT_IMPLEMENTED = "MANAGED_WORKSPACE_NOT_IMPLEMENTED"


@dataclass(frozen=True)
class PostExecCommon:
    """Target-neutral inputs shared by every adapter.

    Adapters may inspect additional fields on the runner request; the runner
    service is responsible for assembling the right ``common`` payload per
    target. ``change_id`` is the runner-issued correlation id (a UUID),
    distinct from any HAM audit id.
    """

    project_id: str | None
    project_root: Path
    summary: str | None
    change_id: str
    # Optional, target-specific inputs. Exactly one of these may be populated
    # depending on ``target``; the runner service constructs the right one.
    pr_inputs: BuildLaneInputs | None = None
    workspace_id: str | None = None


@dataclass(frozen=True)
class OutputResult:
    """Target-neutral post-exec outcome.

    Fields:
        target: Which adapter produced this result.
        build_outcome: Neutral terminal vocabulary. ``"succeeded"`` means the
            target accepted the change (PR opened OR snapshot saved); see
            mapping in :func:`_lift_legacy_build_outcome`.
        target_ref: Opaque, target-specific payload. For ``github_pr`` this is
            ``{"pr_url", "pr_branch", "pr_commit_sha"}``. For
            ``managed_workspace`` (Phase 1 only) this is empty; PR-B will fill
            ``{"snapshot_id", "parent_snapshot_id", "preview_url",
            "changed_paths_count"}``.
        error_summary: ``None`` on success; otherwise a capped error string.
        pr_url / pr_branch / pr_commit_sha: Convenience back-compat fields
            populated only when ``target == "github_pr"``. The runner service
            and downstream persistence still read these directly today;
            future readers should prefer ``target_ref``.
    """

    target: OutputTarget
    build_outcome: BuildOutcome
    target_ref: dict[str, Any] = field(default_factory=dict)
    error_summary: str | None = None
    pr_url: str | None = None
    pr_branch: str | None = None
    pr_commit_sha: str | None = None


@runtime_checkable
class OutputAdapter(Protocol):
    """Post-exec output adapter.

    Both adapters share the same :meth:`emit` signature so the runner service
    can select among them by ``project.output_target`` without conditional
    code paths in the hot loop.
    """

    target: OutputTarget

    def emit(
        self,
        common: PostExecCommon,
        *,
        runner: SubprocessRunner | None = None,
    ) -> OutputResult: ...


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _lift_legacy_build_outcome(legacy: DroidBuildOutcome) -> BuildOutcome:
    """Map a GitHub-PR-specific :data:`DroidBuildOutcome` into the neutral vocabulary.

    - ``pr_opened`` -> ``succeeded``
    - ``nothing_to_change`` -> ``nothing_to_change``
    - ``push_blocked`` -> ``blocked``
    - ``pr_failed`` -> ``failed``
    """
    if legacy == "pr_opened":
        return "succeeded"
    if legacy == "nothing_to_change":
        return "nothing_to_change"
    if legacy == "push_blocked":
        return "blocked"
    return "failed"


def neutral_to_legacy_github_outcome(neutral: BuildOutcome) -> DroidBuildOutcome:
    """Inverse of :func:`_lift_legacy_build_outcome` for wire back-compat.

    Used by the runner service when responding to ``github_pr`` adapter
    runs: HAM-side persistence and the API response still carry the
    PR-shaped ``DroidBuildOutcome`` strings (``pr_opened`` / etc.) so
    pre-PR-A consumers continue to work. For ``managed_workspace`` runs
    the legacy ``build_outcome`` field is omitted on the wire and readers
    fall back to ``output_target`` / ``output_ref`` / ``error_summary``.
    """
    if neutral == "succeeded":
        return "pr_opened"
    if neutral == "nothing_to_change":
        return "nothing_to_change"
    if neutral == "blocked":
        return "push_blocked"
    return "pr_failed"


def _legacy_to_output_result(legacy: BuildLaneResult) -> OutputResult:
    """Lift a PR-shaped :class:`BuildLaneResult` into the neutral :class:`OutputResult`."""
    target_ref: dict[str, Any] = {}
    if legacy.pr_url is not None:
        target_ref["pr_url"] = legacy.pr_url
    if legacy.pr_branch is not None:
        target_ref["pr_branch"] = legacy.pr_branch
    if legacy.pr_commit_sha is not None:
        target_ref["pr_commit_sha"] = legacy.pr_commit_sha
    return OutputResult(
        target="github_pr",
        build_outcome=_lift_legacy_build_outcome(legacy.build_outcome),
        target_ref=target_ref,
        error_summary=legacy.error_summary,
        pr_url=legacy.pr_url,
        pr_branch=legacy.pr_branch,
        pr_commit_sha=legacy.pr_commit_sha,
    )


# ---------------------------------------------------------------------------
# Concrete adapters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GithubPrAdapter:
    """Connected-repo adapter: commits to a feature branch and opens a PR.

    Delegates the real subprocess work to
    :func:`src.ham.droid_runner.build_lane.execute_build_lane_post_exec`,
    preserving every safety check (branch policy, sensitive-path detection,
    no direct push to base, no force-push, no ``commit --amend``,
    no ``gh pr merge`` / ``gh pr close``).

    Requires ``common.pr_inputs`` and a non-``None`` ``runner`` callable.
    The runner host must have ``git`` and ``gh`` available and the
    appropriate GitHub credential (App installation token preferred, PAT
    acceptable for short-lived staging smokes only) mounted out-of-band.
    """

    target: OutputTarget = "github_pr"

    def emit(
        self,
        common: PostExecCommon,
        *,
        runner: SubprocessRunner | None = None,
    ) -> OutputResult:
        if common.pr_inputs is None:
            return OutputResult(
                target="github_pr",
                build_outcome="failed",
                target_ref={},
                error_summary="GithubPrAdapter requires PostExecCommon.pr_inputs",
            )
        if runner is None:
            return OutputResult(
                target="github_pr",
                build_outcome="failed",
                target_ref={},
                error_summary="GithubPrAdapter requires a non-None subprocess runner",
            )
        legacy = execute_build_lane_post_exec(common.pr_inputs, runner=runner)
        return _legacy_to_output_result(legacy)


@dataclass(frozen=True)
class ManagedWorkspaceStubAdapter:
    """Inert managed-workspace adapter.

    Performs zero IO. Always returns a structured failure with
    ``error_summary == MANAGED_WORKSPACE_NOT_IMPLEMENTED`` so the runner
    service and HAM API surface a stable, machine-readable signal that
    the managed snapshot path has not yet been implemented (PR-B scope).

    The stub deliberately ignores ``runner`` — the managed adapter has no
    subprocess pipeline in PR-A. PR-B replaces this with a real adapter
    that computes a diff against the head snapshot, uploads changed files
    to per-tenant Cloud Storage, writes a :class:`ProjectSnapshot` row,
    and atomically updates ``head.json``.
    """

    target: OutputTarget = "managed_workspace"

    def emit(
        self,
        common: PostExecCommon,
        *,
        runner: SubprocessRunner | None = None,
    ) -> OutputResult:
        # Defensive: PR-B should not silently accept stub mode, so we surface
        # a clear, stable error code rather than pretending success.
        del runner  # intentionally unused in PR-A
        return OutputResult(
            target="managed_workspace",
            build_outcome="failed",
            target_ref={},
            error_summary=MANAGED_WORKSPACE_NOT_IMPLEMENTED,
        )


# ---------------------------------------------------------------------------
# Selection helper
# ---------------------------------------------------------------------------


def select_output_adapter(output_target: str | None) -> OutputAdapter:
    """Return the adapter for ``output_target``.

    ``None`` is treated as ``"github_pr"`` only for backward compatibility
    with pre-PR-A runner requests that omit the field. New code paths
    should always pass an explicit target read from
    :class:`src.registry.projects.ProjectRecord.output_target`.
    """
    target = (output_target or "github_pr").strip()
    if target == "github_pr":
        return GithubPrAdapter()
    if target == "managed_workspace":
        return ManagedWorkspaceStubAdapter()
    raise ValueError(f"unknown output_target: {output_target!r}")


__all__ = [
    "BUILD_OUTCOMES",
    "BuildOutcome",
    "GithubPrAdapter",
    "MANAGED_WORKSPACE_NOT_IMPLEMENTED",
    "ManagedWorkspaceStubAdapter",
    "OutputAdapter",
    "OutputResult",
    "OutputTarget",
    "PostExecCommon",
    "neutral_to_legacy_github_outcome",
    "select_output_adapter",
]
