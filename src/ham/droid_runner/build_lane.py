"""
Dark, runner-side helpers for the future Factory Droid Build Lane.

This module is **inert** in P2: nothing in the current API or runner service imports
or invokes :func:`execute_build_lane_post_exec`. It documents and tests the shape of
the post-droid commit / push / PR flow so that a later P3 router can wire it in
without redesigning the contract.

Safety contract (enforced by tests):

- All git / gh calls go through a :data:`SubprocessRunner` seam so tests can run
  without any real subprocess, network, or credential.
- The default runner uses ``subprocess.run(..., shell=False)`` with explicit timeouts.
- Branch names must match :func:`is_safe_branch_name`. ``main`` / ``master`` /
  ``HEAD`` / unprefixed names are rejected.
- The push step pushes the named feature branch only — never ``main``, never
  ``--force``, never ``--force-with-lease``.
- ``commit --amend`` is never used.
- The helper never closes PRs; ``gh pr create`` is the only ``gh`` verb invoked.
- Working trees that touch sensitive paths (``.env*``, ``secrets/``, ``.data/``,
  ``.ham/``, ``logs/``) are refused before any commit is staged.

See ``DROID_BUILD_OUTCOMES`` / :data:`DroidBuildOutcome` in
``src/persistence/control_plane_run.py`` for the persisted-outcome vocabulary.
"""

from __future__ import annotations

import re
import subprocess  # noqa: S404 — guarded: shell=False, timeouts, args list only.
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.persistence.control_plane_run import DROID_BUILD_OUTCOMES, DroidBuildOutcome

__all__ = [
    "DROID_BUILD_OUTCOMES",
    "BuildLaneInputs",
    "BuildLaneResult",
    "CompletedRun",
    "DroidBuildOutcome",
    "SubprocessRunner",
    "detect_sensitive_changes",
    "execute_build_lane_post_exec",
    "generate_branch_name",
    "is_safe_branch_name",
    "make_default_runner",
]

# ---------------------------------------------------------------------------
# Branch-name policy
# ---------------------------------------------------------------------------

BRANCH_PREFIX = "ham-droid/"
_BRANCH_TAIL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{3,63}$")
_FORBIDDEN_TAILS = frozenset({"main", "master", "head", "trunk", "develop", "release"})
_FORBIDDEN_TOP_LEVEL = frozenset({"main", "master", "HEAD", "trunk", "develop", "release"})
_SHORT_ID_RE = re.compile(r"^[a-z0-9]{6,32}$")


def generate_branch_name(*, short_id: str | None = None) -> str:
    """
    Return ``ham-droid/<short-id>``.

    When ``short_id`` is ``None``, a fresh 8-char hex slice is generated. Any
    explicit value (including the empty string) is validated as-is; case is
    not coerced. Raises :class:`ValueError` if the supplied id is not 6-32
    lowercase alphanumeric characters.
    """
    if short_id is None:
        sid = uuid.uuid4().hex[:8]
    else:
        sid = short_id
    if not _SHORT_ID_RE.match(sid):
        raise ValueError(
            "short_id must be 6-32 lowercase alphanumeric characters",
        )
    return f"{BRANCH_PREFIX}{sid}"


def is_safe_branch_name(name: object) -> bool:
    """
    Return ``True`` when ``name`` is a Build-Lane–safe feature branch.

    Forbids: empty, ``main`` / ``master`` / ``HEAD`` (any case), unprefixed names,
    refs paths, leading dash, whitespace / control / git-special characters,
    ``..`` / ``@{`` sequences, and ``*.lock`` tails.
    """
    if not isinstance(name, str) or not name:
        return False
    if len(name) > 200:
        return False
    if name in _FORBIDDEN_TOP_LEVEL or name.lower() in _FORBIDDEN_TAILS:
        return False
    if name.startswith(("/", "-", "refs/")) or name.endswith("/"):
        return False
    if not name.startswith(BRANCH_PREFIX):
        return False
    tail = name[len(BRANCH_PREFIX) :]
    if tail.lower() in _FORBIDDEN_TAILS:
        return False
    if not _BRANCH_TAIL_RE.match(tail):
        return False
    forbidden_chars = (" ", "\t", "\n", "\r", ":", "?", "*", "[", "\\", "~", "^")
    if any(ch in tail for ch in forbidden_chars):
        return False
    if ".." in tail or "@{" in tail or tail.endswith(".lock"):
        return False
    return True


# ---------------------------------------------------------------------------
# Sensitive-path policy
# ---------------------------------------------------------------------------

_SENSITIVE_PREFIXES: tuple[str, ...] = (
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    ".env.development",
    "secrets/",
    "secrets",
    ".secrets/",
    ".data/",
    "data/secrets/",
    "logs/",
    ".logs/",
    ".ham/",
    "provider-data/",
    ".provider-data/",
)

_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "/.env",
    "/secrets/",
    "/.secrets/",
    "/.data/",
    "/logs/",
    "/.ham/",
    "/provider-data/",
)

_SENSITIVE_SUFFIXES: tuple[str, ...] = (".pem", ".key", ".p12", ".pfx")


def _strip_porcelain_path(line: str) -> str | None:
    """Extract the changed path from a ``git status --porcelain`` line."""
    if len(line) < 4 or not line.strip():
        return None
    rest = line[3:]
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1]
    rest = rest.strip()
    if rest.startswith('"') and rest.endswith('"'):
        rest = rest[1:-1]
    return rest or None


def detect_sensitive_changes(porcelain_output: str) -> list[str]:
    """
    Return paths from ``git status --porcelain`` that match the sensitive policy.

    The list preserves order and is capped to the first 10 hits to keep the
    error summary bounded.
    """
    hits: list[str] = []
    for raw_line in porcelain_output.splitlines():
        path = _strip_porcelain_path(raw_line)
        if not path:
            continue
        normalized = "/" + path
        is_sensitive = False
        for pref in _SENSITIVE_PREFIXES:
            if path == pref or path.startswith(pref):
                is_sensitive = True
                break
        if not is_sensitive:
            for sub in _SENSITIVE_SUBSTRINGS:
                if sub in normalized:
                    is_sensitive = True
                    break
        if not is_sensitive:
            for suf in _SENSITIVE_SUFFIXES:
                if path.endswith(suf):
                    is_sensitive = True
                    break
        if is_sensitive and path not in hits:
            hits.append(path)
            if len(hits) >= 10:
                break
    return hits


# ---------------------------------------------------------------------------
# Subprocess seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompletedRun:
    """Subset of :class:`subprocess.CompletedProcess` used by Build Lane."""

    returncode: int
    stdout: str
    stderr: str


SubprocessRunner = Callable[[Sequence[str]], CompletedRun]


def make_default_runner(*, cwd: Path, timeout_sec: int) -> SubprocessRunner:
    """
    Real ``subprocess.run`` runner. ``shell=False``, timeouts on, args list only.

    Not yet wired in production; provided so the contract is testable end-to-end.
    """
    cwd_resolved = Path(cwd).expanduser().resolve()

    def _run(args: Sequence[str]) -> CompletedRun:
        if not args or any(not isinstance(a, str) for a in args):
            raise ValueError("argv must be a non-empty sequence of strings")
        proc = subprocess.run(  # noqa: S603 — args is a list of validated strings; shell=False.
            list(args),
            cwd=str(cwd_resolved),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            shell=False,
        )
        return CompletedRun(
            returncode=int(proc.returncode),
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    return _run


# ---------------------------------------------------------------------------
# Inputs / Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildLaneInputs:
    """Caller-supplied parameters for the post-droid build flow."""

    project_root: Path
    branch_name: str
    commit_message: str
    pr_title: str
    pr_body: str
    base_ref: str = "origin/main"
    remote: str = "origin"
    git_user_name: str = "ham-droid"
    git_user_email: str = "ham-droid@local"


@dataclass(frozen=True)
class BuildLaneResult:
    """Structured outcome persisted on :class:`ControlPlaneRun`."""

    build_outcome: DroidBuildOutcome
    pr_url: str | None
    pr_branch: str | None
    pr_commit_sha: str | None
    error_summary: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PR_URL_RE = re.compile(r"https://github\.com/[^\s]+/pull/\d+")
_MAX_ERROR_SUMMARY = 1500


def _extract_pr_url(stdout: str) -> str | None:
    if not stdout:
        return None
    m = _PR_URL_RE.search(stdout)
    return m.group(0) if m else None


def _base_branch_from_ref(ref: str) -> str:
    cleaned = (ref or "").strip()
    if not cleaned:
        return "main"
    if "/" in cleaned:
        return cleaned.split("/", 1)[1]
    return cleaned


def _cap(text: str, *, n: int = _MAX_ERROR_SUMMARY) -> str:
    s = (text or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _fail(
    *,
    branch: str | None,
    commit: str | None,
    summary: str,
    outcome: DroidBuildOutcome = "pr_failed",
) -> BuildLaneResult:
    return BuildLaneResult(
        build_outcome=outcome,
        pr_url=None,
        pr_branch=branch,
        pr_commit_sha=commit,
        error_summary=_cap(summary),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def execute_build_lane_post_exec(  # noqa: C901 — intentional flat sequential pipeline.
    inputs: BuildLaneInputs,
    *,
    runner: SubprocessRunner,
) -> BuildLaneResult:
    """
    Post-Droid commit / push / PR flow.

    Assumes a prior ``droid exec`` step has already run inside ``project_root``
    and may have left changes in the working tree. The function inspects status,
    refuses sensitive-path changes, commits on a fresh ``ham-droid/<id>`` branch
    when needed, pushes that branch, and opens a GitHub PR via ``gh``.

    Returns one of :data:`DROID_BUILD_OUTCOMES` plus structured PR coordinates
    (``pr_url``, ``pr_branch``, ``pr_commit_sha``).

    All process-spawning IO is delegated to ``runner`` so tests can inject a
    deterministic substitute. **Not** invoked by any router or service in P2.
    """
    if not is_safe_branch_name(inputs.branch_name):
        return _fail(
            branch=None,
            commit=None,
            summary=f"unsafe branch name: {inputs.branch_name!r}",
        )

    base_branch = _base_branch_from_ref(inputs.base_ref)
    if base_branch in _FORBIDDEN_TOP_LEVEL and inputs.branch_name == base_branch:
        return _fail(
            branch=None,
            commit=None,
            summary="refuse to push to the base branch",
        )

    project_root = Path(inputs.project_root).expanduser().resolve()
    if not (project_root / ".git").exists():
        return _fail(
            branch=inputs.branch_name,
            commit=None,
            summary=f"not a git repo: {project_root}",
        )

    status = runner(("git", "status", "--porcelain"))
    if status.returncode != 0:
        return _fail(
            branch=inputs.branch_name,
            commit=None,
            summary=f"git status failed: {status.stderr}",
        )
    if not status.stdout.strip():
        return BuildLaneResult(
            build_outcome="nothing_to_change",
            pr_url=None,
            pr_branch=inputs.branch_name,
            pr_commit_sha=None,
            error_summary=None,
        )

    sensitive = detect_sensitive_changes(status.stdout)
    if sensitive:
        return _fail(
            branch=inputs.branch_name,
            commit=None,
            summary=f"refusing to commit sensitive paths: {sensitive[:5]!r}",
        )

    head = runner(("git", "rev-parse", "--abbrev-ref", "HEAD"))
    current_branch = head.stdout.strip() if head.returncode == 0 else ""
    if current_branch != inputs.branch_name:
        co = runner(("git", "checkout", "-b", inputs.branch_name))
        if co.returncode != 0:
            return _fail(
                branch=inputs.branch_name,
                commit=None,
                summary=f"git checkout -b failed: {co.stderr}",
            )

    add = runner(("git", "add", "--all", "--", "."))
    if add.returncode != 0:
        return _fail(
            branch=inputs.branch_name,
            commit=None,
            summary=f"git add failed: {add.stderr}",
        )

    commit = runner(
        (
            "git",
            "-c",
            f"user.name={inputs.git_user_name}",
            "-c",
            f"user.email={inputs.git_user_email}",
            "commit",
            "-m",
            inputs.commit_message,
        ),
    )
    if commit.returncode != 0:
        return _fail(
            branch=inputs.branch_name,
            commit=None,
            summary=f"git commit failed: {commit.stderr}",
        )

    sha_run = runner(("git", "rev-parse", "HEAD"))
    if sha_run.returncode != 0:
        return _fail(
            branch=inputs.branch_name,
            commit=None,
            summary=f"git rev-parse HEAD failed: {sha_run.stderr}",
        )
    commit_sha = sha_run.stdout.strip() or None

    if inputs.branch_name == base_branch:
        return _fail(
            branch=inputs.branch_name,
            commit=commit_sha,
            summary="refuse to push to the base branch",
        )
    push = runner(
        (
            "git",
            "push",
            inputs.remote,
            f"{inputs.branch_name}:{inputs.branch_name}",
        ),
    )
    if push.returncode != 0:
        return BuildLaneResult(
            build_outcome="push_blocked",
            pr_url=None,
            pr_branch=inputs.branch_name,
            pr_commit_sha=commit_sha,
            error_summary=_cap(f"git push failed: {push.stderr}"),
        )

    pr = runner(
        (
            "gh",
            "pr",
            "create",
            "--base",
            base_branch,
            "--head",
            inputs.branch_name,
            "--title",
            inputs.pr_title,
            "--body",
            inputs.pr_body,
        ),
    )
    if pr.returncode != 0:
        return _fail(
            branch=inputs.branch_name,
            commit=commit_sha,
            summary=f"gh pr create failed: {pr.stderr}",
        )

    pr_url = _extract_pr_url(pr.stdout) or _extract_pr_url(pr.stderr)
    if not pr_url:
        return _fail(
            branch=inputs.branch_name,
            commit=commit_sha,
            summary=f"gh pr create produced no URL: {pr.stdout[:200]!r}",
        )

    return BuildLaneResult(
        build_outcome="pr_opened",
        pr_url=pr_url,
        pr_branch=inputs.branch_name,
        pr_commit_sha=commit_sha,
        error_summary=None,
    )
