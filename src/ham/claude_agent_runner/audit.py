"""Audit event types + sink protocol for the Claude Agent runner."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AuditEvent:
    """One audit-relevant moment in the lifecycle of a Claude Agent run."""

    kind: str
    tool_name: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)
    ts: float = 0.0


class AuditSink(Protocol):
    async def __call__(self, event: AuditEvent) -> None: ...


async def noop_audit_sink(event: AuditEvent) -> None:
    return None


def make_list_audit_sink() -> tuple[Callable[[AuditEvent], Awaitable[None]], list[AuditEvent]]:
    """Return a ``(sink, events)`` pair useful for unit tests."""
    events: list[AuditEvent] = []

    async def _sink(event: AuditEvent) -> None:
        events.append(event)

    return _sink, events


__all__ = [
    "AuditEvent",
    "AuditSink",
    "make_list_audit_sink",
    "noop_audit_sink",
]
