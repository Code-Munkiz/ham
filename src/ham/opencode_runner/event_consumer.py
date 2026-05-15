"""SSE event consumer with Pydantic models.

The published OpenCode docs do not paste canonical SSE event payloads, so
every model below uses ``model_config = ConfigDict(extra="allow")`` and
the runner logs (without echoing values) any unknown ``type`` discriminator
it sees.  This module is the only place the runner asserts knowledge of
the event-type vocabulary.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_LOG = logging.getLogger(__name__)


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class ServerConnected(_Base):
    type: Literal["server.connected"] = "server.connected"


class AssistantMessageChunk(_Base):
    type: Literal["message.part.updated"] = "message.part.updated"
    part: dict[str, Any] = Field(default_factory=dict)


class ToolCallStart(_Base):
    type: Literal["message.tool.start"] = "message.tool.start"
    tool: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)


class FileChange(_Base):
    type: Literal["file.changed"] = "file.changed"
    path: str | None = None
    deleted: bool = False


class PermissionRequest(_Base):
    type: Literal["session.permission.requested"] = "session.permission.requested"
    sessionID: str | None = None  # noqa: N815 — mirror upstream camelCase.
    permissionID: str | None = None  # noqa: N815
    category: str | None = None
    tool: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    path: str | None = None
    command: str | None = None


class SessionComplete(_Base):
    type: Literal["session.idle"] = "session.idle"
    sessionID: str | None = None  # noqa: N815


class SessionError(_Base):
    type: Literal["session.error"] = "session.error"
    message: str | None = None
    error_kind: str | None = None
    sessionID: str | None = None  # noqa: N815 — mirror upstream camelCase.


class UnknownEvent(_Base):
    type: str


_KNOWN: dict[str, type[_Base]] = {
    "server.connected": ServerConnected,
    "message.part.updated": AssistantMessageChunk,
    "message.tool.start": ToolCallStart,
    "file.changed": FileChange,
    "session.permission.requested": PermissionRequest,
    "session.idle": SessionComplete,
    "session.error": SessionError,
}


def parse_event(raw: dict[str, Any]) -> _Base:
    """Materialize a typed event from a raw decoded SSE message.

    Unknown ``type`` values yield :class:`UnknownEvent` so the consumer
    can keep iterating without crashing on upstream schema drift.
    """
    if not isinstance(raw, dict):
        return UnknownEvent(type="__non_dict__")
    type_str = str(raw.get("type") or "").strip()
    cls = _KNOWN.get(type_str)
    if cls is None:
        if type_str:
            _LOG.warning("opencode_runner.unknown_event_type type=%r", type_str)
        return UnknownEvent(**raw) if type_str else UnknownEvent(type="__missing__")
    try:
        return cls(**raw)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning(
            "opencode_runner.event_parse_failed type=%r err=%s",
            type_str,
            type(exc).__name__,
        )
        return UnknownEvent(**raw)


def extract_raw_event_session_id(raw: Mapping[str, Any]) -> str | None:
    """Best-effort session id extraction from an decoded SSE payload dict."""

    for key in ("sessionID", "session_id"):
        raw_val = raw.get(key)
        if raw_val is not None and str(raw_val).strip():
            return str(raw_val).strip()
    sess = raw.get("session")
    if isinstance(sess, dict):
        sid = sess.get("id")
        if sid is not None and str(sid).strip():
            return str(sid).strip()
    return None


def raw_event_matches_active_session(raw: Mapping[str, Any], session_id: str) -> bool:
    """Return True when a global-stream event belongs to ``session_id``.

    ``server.connected`` has no stable session discriminator and must pass
    through. When no session discriminator is present, the event still passes
    (backward compatibility with payloads that omit the field).
    """
    desired = session_id.strip()
    typ = str(raw.get("type") or "").strip()
    if typ == "server.connected":
        return True
    extracted = extract_raw_event_session_id(raw)
    if extracted is None:
        return True
    return extracted == desired


def filter_events_for_session(
    stream: Iterable[dict[str, Any]],
    session_id: str,
) -> Iterator[dict[str, Any]]:
    """Filter a global SSE stream down to ``session_id`` (plus ``server.connected``)."""

    for raw in stream:
        if not isinstance(raw, dict):
            continue
        if raw_event_matches_active_session(raw, session_id):
            yield raw


def consume_events(stream: Iterable[dict[str, Any]]) -> Iterator[_Base]:
    """Yield :class:`_Base`-typed events from any iterable of dicts.

    Production wires the input to ``httpx.Response.iter_lines`` after
    decoding each SSE ``data:`` line as JSON. Tests pass a list directly.
    """
    for raw in stream:
        yield parse_event(raw)


__all__ = [
    "AssistantMessageChunk",
    "FileChange",
    "PermissionRequest",
    "ServerConnected",
    "SessionComplete",
    "SessionError",
    "ToolCallStart",
    "UnknownEvent",
    "consume_events",
    "extract_raw_event_session_id",
    "filter_events_for_session",
    "parse_event",
    "raw_event_matches_active_session",
]
