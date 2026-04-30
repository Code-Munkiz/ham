from __future__ import annotations

import hashlib
import re
from typing import Any


_SECRET_PATTERNS = [
    re.compile(r"\bcrsr_[a-zA-Z0-9_\-]{8,}\b"),
    re.compile(r"\bsk-[a-zA-Z0-9_\-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-\._~\+\/=]{8,}\b", re.I),
]


def provider_capability_matrix() -> dict[str, dict[str, Any]]:
    """Declared Cursor provider capabilities exposed through HAM backend endpoints."""
    return {
        "launch": {"ham_current": True, "cursor_available": True, "implemented_now": True, "follow_up": "none"},
        "status_sync": {"ham_current": True, "cursor_available": True, "implemented_now": True, "follow_up": "none"},
        "event_streaming": {
            "ham_current": "checkpoint_feed",
            "cursor_available": "conversation_endpoint",
            "implemented_now": "conversation_projection",
            "follow_up": "sdk_streaming_adapter_for_real_time",
        },
        "followup_instruction": {"ham_current": True, "cursor_available": True, "implemented_now": True, "follow_up": "none"},
        "cancel_stop": {"ham_current": "best_effort", "cursor_available": "best_effort", "implemented_now": True, "follow_up": "none"},
        "artifacts": {
            "ham_current": "pr_url_only",
            "cursor_available": "limited_in_agent_payload",
            "implemented_now": "safe_projection",
            "follow_up": "expand_when_provider_schema_stable",
        },
        "conversation_state": {
            "ham_current": "none",
            "cursor_available": "conversation_endpoint",
            "implemented_now": "safe_feed_projection",
            "follow_up": "session_resume_markers",
        },
    }


def _safe_text(raw: Any, *, limit: int = 260) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    for p in _SECRET_PATTERNS:
        s = p.sub("[REDACTED]", s)
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def _event_id_for(agent_id: str, observed_at: str, kind: str, source: str, message: str) -> str:
    seed = "|".join([agent_id, observed_at, kind, source, message])
    return f"evt_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"


def _extract_items(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, list):
        out: list[dict[str, Any]] = []
        for x in node:
            out.extend(_extract_items(x))
        return out
    if not isinstance(node, dict):
        return []
    # Prefer known conversation/event arrays first.
    for k in ("events", "messages", "turns", "items"):
        v = node.get(k)
        if isinstance(v, list):
            out: list[dict[str, Any]] = []
            for x in v:
                if isinstance(x, dict):
                    out.append(x)
            if out:
                return out
    return [node]


def map_cursor_conversation_to_feed_events(
    *,
    agent_id: str,
    payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Convert provider conversation payload into bounded safe feed events.
    Never returns raw provider payload fragments or secrets.
    """
    if not isinstance(payload, dict):
        return []
    events: list[dict[str, Any]] = []
    for item in _extract_items(payload):
        observed_at = _safe_text(
            item.get("createdAt")
            or item.get("timestamp")
            or item.get("time")
            or item.get("observed_at")
            or "",
            limit=64,
        ) or "unknown"
        role = _safe_text(item.get("role") or item.get("source") or "cursor", limit=32).lower()
        typ = _safe_text(item.get("type") or item.get("kind") or "event", limit=48).lower()
        message = _safe_text(
            item.get("text")
            or item.get("message")
            or item.get("content")
            or item.get("summary")
            or typ
            or "Provider event",
            limit=260,
        )
        if not message:
            continue
        source = "cursor"
        if role in ("assistant", "agent"):
            source = "cursor"
        elif role in ("user", "ham", "system", "tool"):
            source = "cursor"
        event_id = _event_id_for(agent_id, observed_at, typ, source, message)
        events.append(
            {
                "event_id": event_id,
                "observed_at": observed_at,
                "kind": typ or "provider_event",
                "source": source,
                "message": message,
                "reason_code": None,
            }
        )
    return events[-40:]
