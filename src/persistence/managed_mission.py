"""
Durable, server-side **Managed Cloud Agent** mission history (sibling to ``ControlPlaneRun``).

* Observed/last-seen facts only; no full transcripts or deploy payloads.
* One JSON file per ``mission_registry_id`` under a server-side directory.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.ham.managed_deploy_approval_policy import (
    ManagedDeployApprovalMode,
    normalize_mission_deploy_approval_mode,
)
from src.persistence.control_plane_run import map_cursor_raw_status, utc_now_iso

_MAX_SHORT = 512
_MAX_REASON = 512
_MAX_HEADLINE = 400
_RE_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)

MissionLifecycle = Literal["open", "succeeded", "failed", "archived"]
MissionCheckpoint = Literal[
    "queued",
    "launched",
    "running",
    "blocked",
    "pr_opened",
    "completed",
    "failed",
]

_MAX_CHECKPOINT_REASON = 160
_CHECKPOINT_HISTORY_CAP = 24
_FEED_HISTORY_CAP = 120
_QUEUED_TOKENS = {
    "QUEUED",
    "PENDING",
    "CREATING",
    "NOT_STARTED",
    "SCHEDULED",
    "WAITING",
}
_RUNNING_TOKENS = {
    "RUNNING",
    "IN_PROGRESS",
    "WORKING",
    "PROCESSING",
    "ACTIVE",
}
_FAILED_TOKENS = {
    "FAILED",
    "ERROR",
    "CANCELED",
    "CANCELLED",
    "TIMED_OUT",
    "TIMEOUT",
    "EXPIRED",
}
_COMPLETED_TOKENS = {
    "FINISHED",
    "COMPLETED",
    "COMPLETE",
    "SUCCEEDED",
    "SUCCESS",
    "DONE",
    "CLOSED",
}
_BLOCKED_REASON_SUBSTRINGS = (
    "blocked",
    "approval_required",
    "approval required",
    "awaiting approval",
    "policy",
    "denied",
)


def default_managed_missions_dir() -> Path:
    raw = (os.environ.get("HAM_MANAGED_MISSIONS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".ham" / "managed_missions"


def _cap(s: str | None, n: int) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    if len(t) > n:
        return t[: n - 1] + "…"
    return t


def new_mission_registry_id() -> str:
    return str(uuid.uuid4())


def _normalize_status_token(raw: str | None) -> str | None:
    t = str(raw or "").strip()
    if not t:
        return None
    return re.sub(r"[^A-Z0-9]+", "_", t.upper()).strip("_")


def _checkpoint_from_cursor_status(cursor_status_raw: str | None) -> MissionCheckpoint | None:
    tok = _normalize_status_token(cursor_status_raw)
    if not tok:
        return None
    if tok in _QUEUED_TOKENS:
        return "queued"
    if tok in _RUNNING_TOKENS:
        return "running"
    if tok in _FAILED_TOKENS:
        return "failed"
    if tok in _COMPLETED_TOKENS:
        return "completed"
    return None


def _is_blocked_reason(raw_reason: str | None) -> bool:
    t = str(raw_reason or "").strip().lower()
    if not t:
        return False
    return any(s in t for s in _BLOCKED_REASON_SUBSTRINGS)


def derive_mission_checkpoint(
    *,
    mission_lifecycle: MissionLifecycle,
    cursor_status_raw: str | None,
    status_reason: str | None,
    pr_url: str | None,
    previous_checkpoint: MissionCheckpoint | None,
) -> tuple[MissionCheckpoint, str]:
    if mission_lifecycle == "failed":
        return "failed", "lifecycle_failed"
    if mission_lifecycle == "succeeded":
        return "completed", "lifecycle_succeeded"
    if _is_blocked_reason(status_reason):
        return "blocked", "status_reason_blocked"
    cp = _checkpoint_from_cursor_status(cursor_status_raw)
    if cp is not None:
        if cp == "completed" and pr_url:
            return "pr_opened", "cursor_completed_with_pr"
        return cp, f"cursor_status:{_normalize_status_token(cursor_status_raw) or 'UNKNOWN'}"
    if pr_url:
        return "pr_opened", "pr_url_observed"
    if str(status_reason or "").strip().lower().startswith("managed_launch:created"):
        return "launched", "managed_launch_created"
    if previous_checkpoint is not None:
        return previous_checkpoint, "checkpoint_unchanged"
    return "launched", "default_launched"


class MissionCheckpointEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checkpoint: MissionCheckpoint
    observed_at: str
    reason: str | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def _cap_reason(cls, v: object) -> str | None:
        return _cap(v if v is None else str(v), _MAX_CHECKPOINT_REASON)


class MissionFeedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    observed_at: str
    kind: str
    source: str
    message: str
    reason_code: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("event_id", mode="before")
    @classmethod
    def _norm_event_id(cls, v: object) -> str:
        s = str(v or "").strip()
        return s or f"evt_{uuid.uuid4().hex[:12]}"

    @field_validator("kind", "source", mode="before")
    @classmethod
    def _norm_short(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        return _cap(s or "event", 64) or "event"

    @field_validator("message", mode="before")
    @classmethod
    def _norm_message(cls, v: object) -> str:
        s = str(v or "").strip()
        return _cap(s or "Mission event", 400) or "Mission event"

    @field_validator("reason_code", mode="before")
    @classmethod
    def _norm_reason_code(cls, v: object) -> str | None:
        return _cap(v if v is None else str(v), 120)

    @field_validator("metadata", mode="before")
    @classmethod
    def _norm_metadata(cls, v: object) -> dict[str, Any] | None:
        if v is None:
            return None
        if not isinstance(v, dict):
            return None
        out: dict[str, Any] = {}
        for i, (k, val) in enumerate(v.items()):
            if i >= 8:
                break
            ks = str(k or "").strip()[:64]
            if not ks:
                continue
            if isinstance(val, str):
                out[ks] = val[:200] + ("…" if len(val) > 200 else "")
            elif isinstance(val, (int, float, bool)) or val is None:
                out[ks] = val
            else:
                s = str(val)
                out[ks] = s[:200] + ("…" if len(s) > 200 else "")
        return out or None


def append_mission_checkpoint_event(
    *,
    existing: list[MissionCheckpointEvent],
    checkpoint: MissionCheckpoint,
    observed_at: str,
    reason: str | None,
) -> list[MissionCheckpointEvent]:
    nxt = list(existing)
    nxt.append(
        MissionCheckpointEvent(
            checkpoint=checkpoint,
            observed_at=observed_at,
            reason=reason,
        )
    )
    if len(nxt) > _CHECKPOINT_HISTORY_CAP:
        nxt = nxt[-_CHECKPOINT_HISTORY_CAP:]
    return nxt


def append_mission_feed_event(
    *,
    existing: list[MissionFeedEvent],
    observed_at: str,
    kind: str,
    source: str,
    message: str,
    reason_code: str | None = None,
    event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[MissionFeedEvent]:
    nxt = list(existing)
    nxt.append(
        MissionFeedEvent(
            event_id=str(event_id or "").strip() or f"evt_{uuid.uuid4().hex[:12]}",
            observed_at=observed_at,
            kind=kind,
            source=source,
            message=message,
            reason_code=reason_code,
            metadata=metadata,
        )
    )
    if len(nxt) > _FEED_HISTORY_CAP:
        nxt = nxt[-_FEED_HISTORY_CAP:]
    return nxt


def map_cursor_to_mission_lifecycle(
    *,
    current: MissionLifecycle,
    cursor_status_raw: str | None,
    previous_reason: str | None = None,
) -> tuple[MissionLifecycle, str]:
    """
    Derive v1 ``mission_lifecycle`` from a server-observed Cursor status string.

    Terminal states are sticky: once ``succeeded``/``failed``/``archived``, we do not
    flip back to ``open`` on ambiguous provider noise.
    """
    if current in ("succeeded", "failed", "archived"):
        return current, (previous_reason or "observed_terminal_unchanged")
    cp, reason = map_cursor_raw_status(cursor_status_raw)
    if cp == "succeeded":
        return "succeeded", reason
    if cp == "failed":
        return "failed", reason
    return "open", reason


class ManagedMission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_registry_id: str
    # Identity
    cursor_agent_id: str
    # Optional link to a durable :class:`ControlPlaneRun` row when one exists
    # (e.g. operator/chat launch path with ``ham_run_id``). Nullable for UI-only launch.
    control_plane_ham_run_id: str | None = None

    # Context (observed or launch-time; may be null if unknown)
    mission_handling: Literal["managed"] = "managed"
    # Create-time snapshot of project default deploy approval mode (managed missions only). Legacy JSON omits → ``off``.
    mission_deploy_approval_mode: ManagedDeployApprovalMode = "off"
    uplink_id: str | None = None
    repo_key: str | None = None
    repository_observed: str | None = None
    ref_observed: str | None = None
    branch_name_launch: str | None = None

    # Mission lifecycle (v1; server-observed terminal mapping)
    mission_lifecycle: MissionLifecycle = "open"
    # Last raw status token returned by Cursor (observed, not a derived verdict)
    cursor_status_last_observed: str | None = None
    # Short mapping / observation note (e.g. ``mapped:RUNNING``)
    status_reason_last_observed: str | None = None
    pr_url_last_observed: str | None = None
    mission_checkpoint_latest: MissionCheckpoint | None = None
    mission_checkpoint_updated_at: str | None = None
    mission_checkpoint_reason_last: str | None = None
    mission_checkpoint_events: list[MissionCheckpointEvent] = Field(default_factory=list)
    mission_feed_events: list[MissionFeedEvent] = Field(default_factory=list)

    created_at: str
    updated_at: str
    last_server_observed_at: str

    # Optional last-seen (bounded) — not full Hermes / Vercel bodies
    last_review_severity: str | None = None
    last_review_headline: str | None = None
    last_deploy_state_observed: str | None = None
    last_vercel_mapping_tier: str | None = None
    last_hook_outcome: str | None = None
    last_post_deploy_state: str | None = None
    last_post_deploy_reason_code: str | None = None

    @field_validator(
        "cursor_status_last_observed",
        "status_reason_last_observed",
        "uplink_id",
        "repo_key",
        "repository_observed",
        "ref_observed",
        "pr_url_last_observed",
        "branch_name_launch",
        "last_vercel_mapping_tier",
        "last_post_deploy_state",
        "mission_checkpoint_reason_last",
        mode="before",
    )
    @classmethod
    def _cap_text(cls, v: object) -> str | None:
        return _cap(v if v is None else str(v), _MAX_SHORT)

    @field_validator("last_review_severity", "last_hook_outcome", mode="before")
    @classmethod
    def _cap_short(cls, v: object) -> str | None:
        return _cap(v if v is None else str(v), 64)

    @field_validator("last_review_headline", mode="before")
    @classmethod
    def _cap_headline(cls, v: object) -> str | None:
        return _cap(v if v is None else str(v), _MAX_HEADLINE)

    @field_validator("last_post_deploy_reason_code", mode="before")
    @classmethod
    def _cap_reason(cls, v: object) -> str | None:
        return _cap(v if v is None else str(v), _MAX_REASON)

    @field_validator("control_plane_ham_run_id", "mission_registry_id", mode="before")
    @classmethod
    def _strip_id(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("mission_lifecycle", mode="before")
    @classmethod
    def _v_lifecycle(cls, v: object) -> MissionLifecycle:
        s = str(v or "").strip().lower()
        if s in ("open", "succeeded", "failed", "archived"):
            return cast(MissionLifecycle, s)
        return "open"

    @field_validator("mission_deploy_approval_mode", mode="before")
    @classmethod
    def _v_mission_deploy_approval_mode(cls, v: object) -> ManagedDeployApprovalMode:
        return normalize_mission_deploy_approval_mode(v)


def _json_ready(obj: object) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)  # type: ignore[no-any-return]
    return obj


class ManagedMissionStore:
    """File-backed, one ``{mission_registry_id}.json`` per record."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = (base_dir or default_managed_missions_dir()).expanduser()
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._base

    def _path(self, mission_registry_id: str) -> Path:
        mid = mission_registry_id.strip()
        if not _RE_UUID.match(mid):
            raise ValueError("invalid mission_registry_id")
        return self._base / f"{mid}.json"

    def get(self, mission_registry_id: str) -> ManagedMission | None:
        p = self._path(mission_registry_id)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return ManagedMission.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(
                f"Warning: managed mission read failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return None

    def find_by_cursor_agent_id(self, cursor_agent_id: str) -> ManagedMission | None:
        """Scan store for a mission with this Cursor agent id (O(n) files; v1)."""
        aid = cursor_agent_id.strip()
        if not aid:
            return None
        try:
            for p in self._base.glob("*.json"):
                if not p.is_file() or p.name.endswith(".tmp"):
                    continue
                data = json.loads(p.read_text(encoding="utf-8"))
                if (data.get("cursor_agent_id") or "") == aid:
                    return ManagedMission.model_validate(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return None

    def list_newest_first(self, *, limit: int = 100) -> list[ManagedMission]:
        cap = max(1, min(int(limit), 500))
        out: list[ManagedMission] = []
        try:
            files = [p for p in self._base.glob("*.json") if p.is_file() and not p.name.endswith(".tmp")]

            def _sort_key(path: Path) -> float:
                try:
                    st = path.stat()
                    return float(st.st_mtime)
                except OSError:
                    return 0.0

            for p in sorted(files, key=_sort_key, reverse=True):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    m = ManagedMission.model_validate(data)
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
                out.append(m)
                if len(out) >= cap:
                    break
        except OSError as exc:
            print(
                f"Warning: list managed missions failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
        return out

    def save(self, m: ManagedMission) -> None:
        now = utc_now_iso()
        m2 = m.model_copy(
            update={
                "updated_at": now,
            }
        )
        p = self._path(m2.mission_registry_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            _json_ready(m2),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, p)
