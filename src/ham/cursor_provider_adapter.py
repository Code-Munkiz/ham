from __future__ import annotations

import hashlib
import re
from typing import Any

_METADATA_KEYS_CAP = 8
_METADATA_STR_LIMIT = 200

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
            "ham_current": "rest_polling_checkpoint_and_conversation",
            "cursor_available": "conversation_endpoint",
            "implemented_now": "rest_projection_only",
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
            "ham_current": "rest_snapshot",
            "cursor_available": "conversation_endpoint",
            "implemented_now": "safe_feed_projection",
            "follow_up": "session_resume_markers",
        },
    }


def provider_projection_envelope(
    *,
    provider_error: str | None,
    mode: str = "rest_projection",
    native_realtime_stream: bool = False,
) -> dict[str, Any]:
    """
    Declares REST-only projection semantics for managed-mission feeds.
    ``native_realtime_stream`` is always false for the current HTTP client.
    """
    if not provider_error:
        return {
            "provider": "cursor",
            "mode": mode,
            "native_realtime_stream": native_realtime_stream,
            "status": "ok",
            "reason": None,
        }
    tail = provider_error.rsplit(":", 1)[-1].strip()
    code: int | None = int(tail) if tail.isdigit() else None
    if provider_error == "provider_key_missing":
        status = "unavailable"
    elif code in (401, 403, 404):
        status = "unavailable"
    elif code is not None and code >= 500:
        status = "error"
    elif provider_error.startswith("provider_"):
        status = "unavailable"
    else:
        status = "error"
    return {
        "provider": "cursor",
        "mode": mode,
        "native_realtime_stream": native_realtime_stream,
        "status": status,
        "reason": provider_error,
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


def _redact_shallow_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for i, (k, v) in enumerate(raw.items()):
        if i >= _METADATA_KEYS_CAP:
            break
        ks = _safe_text(str(k), limit=64)
        if not ks:
            continue
        if isinstance(v, str):
            out[ks] = _safe_text(v, limit=_METADATA_STR_LIMIT)
        elif isinstance(v, (int, float, bool)) or v is None:
            out[ks] = v
        else:
            out[ks] = _safe_text(str(v), limit=_METADATA_STR_LIMIT)
    return out


def _provider_stable_id(item: dict[str, Any]) -> str | None:
    for k in ("id", "messageId", "message_id", "eventId", "event_id", "uuid", "turnId", "turn_id"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:128]
        if isinstance(v, int):
            return str(v)
    return None


def _normalize_projection_kind(*, role: str, typ: str, message: str) -> str:
    r = (role or "").lower()
    t = (typ or "").lower()
    msg_l = (message or "").lower()
    if any(x in t for x in ("error", "failed", "failure", "exception")) or r == "error":
        return "error"
    if any(x in t for x in ("complete", "finished", "done", "succeeded", "success")):
        return "completed"
    if "github.com" in msg_l and "/pull/" in msg_l:
        return "pr_url"
    if "artifact" in t or "attachment" in t:
        return "artifact"
    if r in ("assistant", "agent"):
        return "assistant_message"
    if r == "user":
        return "user_message"
    if r in ("tool", "system") or "tool" in t or "progress" in t:
        return "status"
    return "status"


def _event_id_for(
    agent_id: str,
    observed_at: str,
    kind: str,
    source: str,
    message: str,
    *,
    provider_stable_id: str | None = None,
) -> str:
    if provider_stable_id:
        seed = f"cursor|{agent_id}|{provider_stable_id}".encode("utf-8")
        return f"evt_{hashlib.sha1(seed).hexdigest()[:16]}"
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


def _sort_key_time_id(observed_at: str, event_id: str) -> tuple[str, str]:
    t = (observed_at or "").strip() or "unknown"
    if t == "unknown":
        t = "\uffff" * 4
    return (t, event_id)


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
    by_id: dict[str, dict[str, Any]] = {}
    for item in _extract_items(payload):
        observed_at = _safe_text(
            item.get("createdAt")
            or item.get("timestamp")
            or item.get("time")
            or item.get("observed_at")
            or "",
            limit=64,
        ) or "unknown"
        role_raw = item.get("role") or item.get("source") or "cursor"
        role = _safe_text(role_raw, limit=32).lower()
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
        norm_kind = _normalize_projection_kind(role=role, typ=typ, message=message)
        pid = _provider_stable_id(item)
        event_id = _event_id_for(
            agent_id,
            observed_at,
            norm_kind,
            source,
            message,
            provider_stable_id=pid,
        )
        meta_src: dict[str, Any] = {
            "provider_role": _safe_text(role_raw, limit=48),
            "provider_type": typ,
        }
        if pid:
            meta_src["provider_message_id"] = pid
        meta = _redact_shallow_metadata(meta_src)
        by_id[event_id] = {
            "event_id": event_id,
            "observed_at": observed_at,
            "kind": norm_kind,
            "source": source,
            "message": message,
            "reason_code": _safe_text(f"cursor_typ:{typ}", limit=120) if typ else None,
            "metadata": meta or None,
        }
    ordered = sorted(by_id.values(), key=lambda e: _sort_key_time_id(str(e["observed_at"]), str(e["event_id"])))
    return ordered[-40:]


def map_cursor_sdk_bridge_to_feed_events(
    *,
    agent_id: str,
    rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Convert normalized SDK bridge JSONL rows into bounded safe feed events.
    """
    if not isinstance(rows, list):
        return []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        observed_at = _safe_text(row.get("time") or row.get("observed_at") or "", limit=64)
        if not observed_at:
            continue
        kind = _safe_text(row.get("kind") or "", limit=32).lower()
        if not kind:
            continue
        if kind not in {
            "assistant_message",
            "tool_event",
            "thinking",
            "status",
            "artifact",
            "pr_url",
            "error",
            "completed",
        }:
            kind = "status"
        message = _safe_text(row.get("message") or "", limit=260)
        if not message:
            continue
        provider_id = _safe_text(row.get("event_id"), limit=128) or None
        eid = _event_id_for(
            agent_id,
            observed_at,
            kind,
            "cursor",
            message,
            provider_stable_id=provider_id,
        )
        raw_meta = row.get("metadata")
        if not isinstance(raw_meta, dict):
            raw_meta = {}
        run_id = _safe_text(row.get("run_id"), limit=80)
        if run_id:
            raw_meta = {**raw_meta, "run_id": run_id}
        meta = _redact_shallow_metadata(raw_meta)
        by_id[eid] = {
            "event_id": eid,
            "observed_at": observed_at,
            "kind": kind,
            "source": "cursor",
            "message": message,
            "reason_code": _safe_text(f"cursor_sdk:{kind}", limit=120),
            "metadata": meta or None,
        }
    ordered = sorted(by_id.values(), key=lambda e: _sort_key_time_id(str(e["observed_at"]), str(e["event_id"])))
    return ordered[-60:]
