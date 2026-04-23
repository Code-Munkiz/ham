"""
Durable HAM control-plane run records (provider launches), separate from bridge `RunStore`.

Spec: `docs/CONTROL_PLANE_RUN.md`
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_LAST_PROVIDER_STATUS = 256
MAX_SUMMARY_CHARS = 2_000
MAX_ERROR_SUMMARY_CHARS = 2_000
MAX_STATUS_REASON_CHARS = 512


def default_control_plane_runs_dir() -> Path:
    raw = (os.environ.get("HAM_CONTROL_PLANE_RUNS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".ham" / "control_plane_runs"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cap_last_provider_status(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) > MAX_LAST_PROVIDER_STATUS:
        return s[: MAX_LAST_PROVIDER_STATUS - 1] + "…"
    return s


def cap_summary(s: str | None) -> str | None:
    if s is None:
        return None
    t = str(s)
    if len(t) > MAX_SUMMARY_CHARS:
        return t[: MAX_SUMMARY_CHARS - 1] + "…"
    return t


def cap_error_summary(s: str | None) -> str | None:
    if s is None:
        return None
    t = str(s)
    if len(t) > MAX_ERROR_SUMMARY_CHARS:
        return t[: MAX_ERROR_SUMMARY_CHARS - 1] + "…"
    return t


def cap_status_reason(s: str | None) -> str:
    t = (s or "").strip() or "unspecified"
    if len(t) > MAX_STATUS_REASON_CHARS:
        return t[: MAX_STATUS_REASON_CHARS - 1] + "…"
    return t


class ControlPlaneProvider(str, Enum):
    cursor_cloud_agent = "cursor_cloud_agent"
    factory_droid = "factory_droid"


ControlPlaneStatus = Literal["running", "succeeded", "failed", "unknown"]


# Conservative Cursor Cloud Agent string mapping (see tests for sample values).
_CURS_SUCCEEDED = frozenset(
    s.upper() for s in ("FINISHED", "COMPLETED", "SUCCEEDED", "SUCCESS", "DONE")
)
_CURS_FAILED = frozenset(
    s.upper() for s in ("FAILED", "ERROR", "CANCELLED", "CANCELED", "ERRORED")
)
_CURS_RUNNING = frozenset(
    s.upper()
    for s in (
        "CREATING",
        "RUNNING",
        "PENDING",
        "QUEUED",
        "STARTING",
        "WORKING",
    )
)


def map_cursor_raw_status(
    status: str | None,
) -> tuple[ControlPlaneStatus, str]:
    """
    Map provider-reported status to HAM lifecycle.

    - Explicit terminal success -> succeeded
    - Explicit terminal failure -> failed
    - Known in-flight tokens -> running
    - Missing / unmapped / empty -> unknown
    """
    if not status or not str(status).strip():
        return "unknown", "empty_provider_status"
    token = str(status).strip()
    u = re.sub(r"\s+", " ", token).upper()
    if u in _CURS_SUCCEEDED:
        return "succeeded", f"mapped:{u}"
    if u in _CURS_FAILED:
        return "failed", f"mapped:{u}"
    if u in _CURS_RUNNING:
        return "running", f"mapped:{u}"
    return "unknown", f"unmapped_status:{u[:64]}"


def droid_outcome_to_ham_status(
    *,
    ok: bool,
    timed_out: bool,
    exit_code: int | None,
    had_runner_body: bool,
) -> tuple[ControlPlaneStatus, str]:
    if timed_out:
        return "failed", "droid:timed_out"
    if not had_runner_body and exit_code is None:
        return "failed", "droid:runner_unavailable"
    if exit_code is not None and exit_code == 0 and ok:
        return "succeeded", f"droid:exit {exit_code}"
    if exit_code is not None and exit_code != 0:
        return "failed", f"droid:exit {exit_code}"
    if not ok:
        return "failed", "droid:launch_not_ok"
    return "unknown", "droid:ambiguous_outcome"


class ControlPlaneProviderAuditRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sink: Literal["cursor_jsonl", "droid_jsonl", "project_mirror"]
    path: str | None = None


class ControlPlaneAuditRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_audit_id: str | None = None
    provider_audit: ControlPlaneProviderAuditRef | None = None


def _json_ready(obj: object) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)  # type: ignore[no-any-return]
    return obj


class ControlPlaneRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ham_run_id: str
    version: int = 1
    provider: str
    action_kind: str = "launch"
    project_id: str
    created_by: dict[str, Any] | None = None
    created_at: str
    updated_at: str
    committed_at: str
    started_at: str | None = None
    finished_at: str | None = None
    last_observed_at: str | None = None
    status: str
    status_reason: str
    proposal_digest: str
    base_revision: str
    external_id: str | None = None
    workflow_id: str | None = None
    summary: str | None = None
    error_summary: str | None = None
    last_provider_status: str | None = None
    audit_ref: ControlPlaneAuditRef | None = None
    project_root: str | None = None

    @field_validator("last_provider_status", mode="before")
    @classmethod
    def _v_last_provider_status(cls, v: object) -> str | None:
        return cap_last_provider_status(v if v is None else str(v))  # type: ignore[return-value]


def new_ham_run_id() -> str:
    return str(uuid.uuid4())


class ControlPlaneRunStore:
    """File-backed one JSON per ``ham_run_id`` under a server-global directory (default)."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = (base_dir or default_control_plane_runs_dir()).expanduser()
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._base

    def _path(self, ham_run_id: str) -> Path:
        if not re.match(r"^[0-9a-f-]{36}$", ham_run_id, re.I):
            raise ValueError("invalid ham_run_id")
        return self._base / f"{ham_run_id}.json"

    def _path_mirror(self, project_root: str, ham_run_id: str) -> Path:
        return (
            Path(project_root).expanduser().resolve()
            / ".ham"
            / "control_plane"
            / "runs"
            / f"{ham_run_id}.json"
        )

    def get(self, ham_run_id: str) -> ControlPlaneRun | None:
        p = self._path(ham_run_id)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return ControlPlaneRun.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(
                f"Warning: control plane run read failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return None

    def find_by_project_and_external(
        self,
        *,
        project_id: str,
        provider: str,
        external_id: str,
    ) -> ControlPlaneRun | None:
        eid = external_id.strip()
        if not eid:
            return None
        try:
            for p in self._base.glob("*.json"):
                if not p.is_file():
                    continue
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("project_id") == project_id and data.get("provider") == provider:
                    if (data.get("external_id") or "") == eid:
                        return ControlPlaneRun.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return None

    def find_by_provider_and_external(
        self,
        *,
        provider: str,
        external_id: str,
    ) -> ControlPlaneRun | None:
        """
        Find a run by provider + external id (no project filter).

        Used to attach optional ``control_plane_ham_run_id`` for managed mission rows.
        O(n) over run files; acceptable for v1/volume.
        """
        eid = external_id.strip()
        prov = provider.strip()
        if not eid or not prov:
            return None
        try:
            for p in self._base.glob("*.json"):
                if not p.is_file():
                    continue
                data = json.loads(p.read_text(encoding="utf-8"))
                if str(data.get("provider") or "") != prov:
                    continue
                if (data.get("external_id") or "") == eid:
                    return ControlPlaneRun.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return None

    def list_for_project(
        self,
        project_id: str,
        *,
        provider: str | None = None,
        limit: int = 100,
    ) -> list[ControlPlaneRun]:
        """Newest first; optional exact ``provider`` filter and ``limit`` (capped 1–500)."""
        pid = project_id.strip()
        if not pid:
            return []
        cap = max(1, min(int(limit), 500))
        prov = provider.strip() if (provider and str(provider).strip()) else None
        out: list[ControlPlaneRun] = []
        try:
            for p in sorted(self._base.glob("*.json"), key=lambda x: x.name, reverse=True):
                if not p.is_file():
                    continue
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("project_id") != pid:
                    continue
                if prov and str(data.get("provider") or "") != prov:
                    continue
                out.append(ControlPlaneRun.model_validate(data))
                if len(out) >= cap:
                    break
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(
                f"Warning: list control plane runs failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
        return out

    def save(self, run: ControlPlaneRun, *, project_root_for_mirror: str | None = None) -> None:
        run = run.model_copy(
            update={
                "summary": cap_summary(run.summary),
                "error_summary": cap_error_summary(run.error_summary),
                "status_reason": cap_status_reason(run.status_reason),
            }
        )
        p = self._path(run.ham_run_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            _json_ready(run),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, p)

        if project_root_for_mirror and str(project_root_for_mirror).strip():
            pr = Path(project_root_for_mirror).expanduser().resolve()
            if pr.is_dir():
                try:
                    mp = self._path_mirror(str(pr), run.ham_run_id)
                    mp.parent.mkdir(parents=True, exist_ok=True)
                    mtmp = mp.with_suffix(".json.tmp")
                    mtmp.write_text(payload, encoding="utf-8")
                    os.replace(mtmp, mp)
                except OSError:
                    pass
