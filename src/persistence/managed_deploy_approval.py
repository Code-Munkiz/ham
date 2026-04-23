"""
Sibling store for **managed** deploy hook approval decisions (separate from mission registry row).

* Bounded, auditable records; one JSON file per ``approval_id``.
* Latest decision per ``cursor_agent_id`` is derived by scan (v1 volume).
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from src.persistence.control_plane_run import utc_now_iso

_RE_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
_MAX_NOTE = 2_000
_MAX_JUST = 1_200
_MAX_INPUTS_JSON = 4_000

DeployApprovalState = Literal["pending", "approved", "denied"]
ApprovalSource = Literal["operator_ui", "api", "script"]


def default_managed_deploy_approvals_dir() -> Path:
    raw = (os.environ.get("HAM_MANAGED_DEPLOY_APPROVALS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".ham" / "managed_deploy_approvals"


def new_approval_id() -> str:
    return str(uuid.uuid4())


class ApprovalActor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["clerk", "unknown"] = "clerk"
    user_id: str | None = None
    email: str | None = None


class ManagedDeployApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    mission_registry_id: str | None = None
    cursor_agent_id: str
    state: DeployApprovalState
    decision_at: str
    actor: ApprovalActor | None = None
    source: ApprovalSource = "operator_ui"
    note: str | None = None
    override: bool = False
    override_justification: str | None = None
    inputs_summary: dict[str, Any] | None = None

    @field_validator("note", mode="before")
    @classmethod
    def _v_note(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return s[: _MAX_NOTE - 1] + "…" if len(s) > _MAX_NOTE else s

    @field_validator("override_justification", mode="before")
    @classmethod
    def _v_just(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return s[: _MAX_JUST - 1] + "…" if len(s) > _MAX_JUST else s

    @field_validator("inputs_summary", mode="before")
    @classmethod
    def _v_insum(cls, v: object) -> dict[str, Any] | None:
        if v is None or not isinstance(v, dict):
            return None
        try:
            blob = json.dumps(v, ensure_ascii=True)[:_MAX_INPUTS_JSON]
            return json.loads(blob)
        except (TypeError, ValueError):
            return None


def _json_ready(obj: object) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)  # type: ignore[no-any-return]
    return obj


class ManagedDeployApprovalStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = (base_dir or default_managed_deploy_approvals_dir()).expanduser()
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._base

    def _path(self, approval_id: str) -> Path:
        aid = approval_id.strip()
        if not _RE_UUID.match(aid):
            raise ValueError("invalid approval_id")
        return self._base / f"{aid}.json"

    def get(self, approval_id: str) -> ManagedDeployApproval | None:
        p = self._path(approval_id)
        if not p.is_file():
            return None
        try:
            return ManagedDeployApproval.model_validate(
                json.loads(p.read_text(encoding="utf-8")),
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(
                f"Warning: deploy approval read failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return None

    def save(self, row: ManagedDeployApproval) -> None:
        p = self._path(row.approval_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            _json_ready(row),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, p)

    def latest_for_cursor_agent_id(self, cursor_agent_id: str) -> ManagedDeployApproval | None:
        """Newest by ``decision_at`` (ISO sort is safe for HAM ``utc_now_iso`` format)."""
        aid = cursor_agent_id.strip()
        if not aid:
            return None
        rows: list[ManagedDeployApproval] = []
        try:
            for p in self._base.glob("*.json"):
                if not p.is_file() or p.name.endswith(".tmp"):
                    continue
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    m = ManagedDeployApproval.model_validate(data)
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
                if m.cursor_agent_id == aid and m.state in ("approved", "denied"):
                    rows.append(m)
        except OSError as exc:
            print(
                f"Warning: deploy approval scan failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return None
        if not rows:
            return None
        rows.sort(key=lambda r: r.decision_at, reverse=True)
        return rows[0]
