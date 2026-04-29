"""
File-backed store for **Browser Operator** action approval proposals (Phase 2).

* Bounded, redacted records; one JSON file per ``proposal_id``.
* No secrets, auth headers, tokens, query strings, or full local paths are persisted.
* Sibling pattern of ``ManagedDeployApprovalStore`` (one JSON file per id, no DB).
* Decoupled from ``ControlPlaneRun`` and ``RunStore`` — this is per-action audit only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.persistence.control_plane_run import utc_now_iso

_RE_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)

# Field caps (defensive bounds; keep proposal records small and PII-free).
MAX_OWNER_KEY = 128
MAX_SESSION_ID = 128
MAX_NOTE = 1_000
MAX_PROPOSER_LABEL = 256
MAX_URL = 4_096
MAX_SELECTOR = 2_048
MAX_TEXT = 4_000
MAX_KEY = 64
MAX_ERROR = 1_000

# Action types allowed in v1 (Phase 2).
BrowserActionType = Literal[
    "browser.navigate",
    "browser.click_xy",
    "browser.scroll",
    "browser.key",
    "browser.type",
    "browser.reset",
]
ALLOWED_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "browser.navigate",
        "browser.click_xy",
        "browser.scroll",
        "browser.key",
        "browser.type",
        "browser.reset",
    }
)

# Lifecycle states.
ProposalState = Literal[
    "proposed",
    "approved",
    "denied",
    "executed",
    "failed",
    "expired",
]


def default_browser_proposals_dir() -> Path:
    raw = (os.environ.get("HAM_BROWSER_PROPOSALS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".ham" / "browser_proposals"


def new_proposal_id() -> str:
    return str(uuid.uuid4())


def _cap(s: object, cap: int) -> str | None:
    if s is None:
        return None
    v = str(s)
    if not v:
        return None
    return v[: cap - 1] + "\u2026" if len(v) > cap else v


def redact_url(raw: str) -> str:
    """
    Keep ``scheme://host[:port]/path`` only; drop query and fragment to avoid
    leaking secrets/tokens commonly present in URL parameters.
    """
    p = urlparse(raw.strip())
    rebuilt = urlunparse((p.scheme, p.netloc, p.path or "/", "", "", ""))
    if len(rebuilt) > MAX_URL:
        rebuilt = rebuilt[: MAX_URL - 1] + "\u2026"
    return rebuilt


class ProposerActor(BaseModel):
    """
    Originator of the proposal. ``label`` is operator-chosen and capped; no
    secrets, paths, or tokens belong here.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["operator", "agent", "chat", "unknown"] = "operator"
    label: str | None = None

    @field_validator("label", mode="before")
    @classmethod
    def _v_label(cls, v: object) -> str | None:
        return _cap(v, MAX_PROPOSER_LABEL)


class BrowserActionPayload(BaseModel):
    """
    Bounded action description. ``action_type`` is restricted to v1 allowlist.
    Per-action params are optional and validated at proposal-create time.
    """

    model_config = ConfigDict(extra="forbid")

    action_type: BrowserActionType
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    clear_first: bool | None = None
    x: float | None = None
    y: float | None = None
    delta_x: float | None = None
    delta_y: float | None = None
    key: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def _v_url(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return redact_url(s)

    @field_validator("selector", mode="before")
    @classmethod
    def _v_selector(cls, v: object) -> str | None:
        return _cap(v, MAX_SELECTOR)

    @field_validator("text", mode="before")
    @classmethod
    def _v_text(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v)
        if not s:
            return ""
        return s[: MAX_TEXT - 1] + "\u2026" if len(s) > MAX_TEXT else s

    @field_validator("key", mode="before")
    @classmethod
    def _v_key(cls, v: object) -> str | None:
        return _cap(v, MAX_KEY)


class BrowserActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    session_id: str = Field(min_length=1, max_length=MAX_SESSION_ID)
    owner_key: str = Field(min_length=1, max_length=MAX_OWNER_KEY)
    state: ProposalState
    action: BrowserActionPayload
    proposer: ProposerActor

    created_at: str
    expires_at: str
    decided_at: str | None = None
    decision_note: str | None = None
    executed_at: str | None = None
    result_status: Literal["ok", "error"] | None = None
    result_last_error: str | None = None

    @field_validator("decision_note", mode="before")
    @classmethod
    def _v_dnote(cls, v: object) -> str | None:
        return _cap(v, MAX_NOTE)

    @field_validator("result_last_error", mode="before")
    @classmethod
    def _v_err(cls, v: object) -> str | None:
        return _cap(v, MAX_ERROR)


def _json_ready(obj: object) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    return obj


class BrowserProposalStore:
    """
    Tiny file-backed store. One JSON file per proposal under ``base_dir``.
    Latest-by-session derived by directory scan (v1 volume is tiny per session).
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = (base_dir or default_browser_proposals_dir()).expanduser()
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._base

    def _path(self, proposal_id: str) -> Path:
        pid = proposal_id.strip()
        if not _RE_UUID.match(pid):
            raise ValueError("invalid proposal_id")
        return self._base / f"{pid}.json"

    def get(self, proposal_id: str) -> BrowserActionProposal | None:
        p = self._path(proposal_id)
        if not p.is_file():
            return None
        try:
            return BrowserActionProposal.model_validate(
                json.loads(p.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(
                f"Warning: browser proposal read failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return None

    def save(self, row: BrowserActionProposal) -> None:
        p = self._path(row.proposal_id)
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

    def list_for_session(
        self,
        *,
        session_id: str,
        owner_key: str,
        limit: int = 64,
    ) -> list[BrowserActionProposal]:
        """Newest by ``created_at`` first; only entries owned by ``owner_key``."""
        sid = session_id.strip()
        ok = owner_key.strip()
        if not sid or not ok:
            return []
        rows: list[BrowserActionProposal] = []
        try:
            for path in self._base.glob("*.json"):
                if not path.is_file() or path.name.endswith(".tmp"):
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    m = BrowserActionProposal.model_validate(data)
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
                if m.session_id == sid and m.owner_key == ok:
                    rows.append(m)
        except OSError as exc:
            print(
                f"Warning: browser proposal scan failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return []
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[: max(0, int(limit))]

    def count_pending_for_session(self, *, session_id: str, owner_key: str) -> int:
        return sum(
            1
            for p in self.list_for_session(session_id=session_id, owner_key=owner_key, limit=10_000)
            if p.state == "proposed"
        )


__all__ = [
    "ALLOWED_ACTION_TYPES",
    "BrowserActionPayload",
    "BrowserActionProposal",
    "BrowserActionType",
    "BrowserProposalStore",
    "MAX_TEXT",
    "MAX_URL",
    "ProposalState",
    "ProposerActor",
    "default_browser_proposals_dir",
    "new_proposal_id",
    "redact_url",
    "utc_now_iso",
]
