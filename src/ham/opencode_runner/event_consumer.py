"""SSE event consumer with Pydantic models.

The published OpenCode docs do not paste canonical SSE event payloads, so
every model below uses ``model_config = ConfigDict(extra="allow")`` and
the runner logs (without echoing values) any unknown ``type`` discriminator
it sees.  This module is the only place the runner asserts knowledge of
the event-type vocabulary.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
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
    "parse_event",
]
