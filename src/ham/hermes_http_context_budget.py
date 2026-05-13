"""Bound OpenAI-shaped ``messages`` before Hermes HTTP /v1/chat/completions uploads.

Hermes rejects oversized JSON bodies with HTTP 413. Session persistence replays gateway
failure strings as ordinary assistant turns, which compounds payload size unless filtered.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

STRUCT_PREFIX_ROLES = frozenset({"system", "developer"})


def _flatten_text_content(content: Any) -> str:
    """Plain text for heuristic matching (assistant + user multimodal-aware)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text" and isinstance(p.get("text"), str):
                parts.append(p["text"])
            if p.get("type") == "image_url":
                parts.append("[image]")
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _assistant_starts_like_gateway_boilerplate(text_lower: str) -> bool:
    """Match user-visible Hermes/OpenRouter/router failure replies (persisted verbatim)."""
    starts = (
        "the model gateway stopped responding",
        "the model gateway refused authorization",
        "the model gateway endpoint was not found",
        "the model gateway rejected the request or model id",
        "the model gateway rejected the request",
        "the model gateway rate-limited this request",
        "the model gateway returned a server error",
        "chat could not reach the model gateway",
        "the assistant stream stalled",
        "this reply took too long overall",
        "chat is misconfigured on the server",
        "openrouter rejected the selected model",
        "mock assistant reply",
    )
    if any(text_lower.startswith(p) for p in starts):
        return True
    if text_lower.startswith("connection interrupted"):
        return True
    if "\n\nconnection interrupted" in text_lower:
        return True
    return False


def is_synthetic_failure_assistant_message(message: dict[str, Any]) -> bool:
    if str(message.get("role") or "") != "assistant":
        return False
    text_lower = _flatten_text_content(message.get("content")).lower()
    if not text_lower:
        return False
    return _assistant_starts_like_gateway_boilerplate(text_lower)


def _wire_chars(message: dict[str, Any]) -> int:
    return len(json.dumps(message, ensure_ascii=False, separators=(",", ":")))


def messages_wire_total_chars(messages: list[dict[str, Any]]) -> int:
    return sum(_wire_chars(m) for m in messages)


def _deepcopy_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Chat payloads are JSON-serializable dicts/lists/strings.
    return json.loads(json.dumps(messages))


def default_max_wire_chars() -> int:
    raw = (os.environ.get("HAM_HERMES_HTTP_CONTEXT_MAX_CHARS") or "").strip()
    if raw:
        try:
            return max(4096, int(raw))
        except ValueError:
            pass
    return 120_000


@dataclass(frozen=True)
class HermesHttpContextBudgetResult:
    original_message_count: int
    final_message_count: int
    original_char_count: int
    final_char_count: int
    dropped_error_message_count: int
    truncated_for_gateway_budget: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "original_message_count": self.original_message_count,
            "final_message_count": self.final_message_count,
            "original_char_count": self.original_char_count,
            "final_char_count": self.final_char_count,
            "dropped_error_message_count": self.dropped_error_message_count,
            "truncated_for_gateway_budget": self.truncated_for_gateway_budget,
        }


def _truncate_latest_user_wire_fit(msgs: list[dict[str, Any]], cap: int) -> bool:
    """Mutates ``msgs`` in place; trims the last user textual content until under cap."""
    modified = False
    while msgs and messages_wire_total_chars(msgs) > cap:
        last = msgs[-1]
        if str(last.get("role") or "") != "user":
            break
        content = last.get("content")
        if isinstance(content, str):
            step = max(256, len(content) // 10)
            if len(content) <= 256:
                break
            last["content"] = content[step:]
            modified = True
            continue
        if isinstance(content, list):
            trimmed = False
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    txt = part["text"]
                    if len(txt) <= 128:
                        continue
                    chop = max(128, len(txt) // 10)
                    part["text"] = txt[chop:]
                    trimmed = True
                    break
            if trimmed:
                modified = True
                continue
            break
        break
    return modified


def apply_hermes_http_context_budget(
    messages: list[dict[str, Any]],
    *,
    max_wire_chars: int | None = None,
) -> tuple[list[dict[str, Any]], HermesHttpContextBudgetResult]:
    cap = max_wire_chars if max_wire_chars is not None else default_max_wire_chars()
    orig_count = len(messages)
    orig_chars = messages_wire_total_chars(messages)

    filtered: list[dict[str, Any]] = []
    dropped_error_message_count = 0
    for m in messages:
        if is_synthetic_failure_assistant_message(m):
            dropped_error_message_count += 1
            continue
        filtered.append(m)

    truncated_for_gateway_budget = False

    if not filtered:
        result = HermesHttpContextBudgetResult(
            original_message_count=orig_count,
            final_message_count=0,
            original_char_count=orig_chars,
            final_char_count=0,
            dropped_error_message_count=dropped_error_message_count,
            truncated_for_gateway_budget=False,
        )
        return [], result

    if messages_wire_total_chars(filtered) <= cap:
        return list(filtered), HermesHttpContextBudgetResult(
            original_message_count=orig_count,
            final_message_count=len(filtered),
            original_char_count=orig_chars,
            final_char_count=messages_wire_total_chars(filtered),
            dropped_error_message_count=dropped_error_message_count,
            truncated_for_gateway_budget=truncated_for_gateway_budget,
        )

    working = _deepcopy_messages(filtered)

    p = 0
    while p < len(working) and str(working[p].get("role") or "") in STRUCT_PREFIX_ROLES:
        p += 1
    prefix = working[:p]
    rest = working[p:]
    idx_last_user: int | None = None
    for j in range(len(rest) - 1, -1, -1):
        if rest[j].get("role") == "user":
            idx_last_user = j
            break

    if idx_last_user is None:
        middle = rest
        while middle and messages_wire_total_chars(prefix + middle) > cap:
            middle.pop(0)
            truncated_for_gateway_budget = True
        candidate = prefix + middle
        if messages_wire_total_chars(candidate) > cap and _truncate_latest_user_wire_fit(candidate, cap):
            truncated_for_gateway_budget = True
        return candidate, HermesHttpContextBudgetResult(
            original_message_count=orig_count,
            final_message_count=len(candidate),
            original_char_count=orig_chars,
            final_char_count=messages_wire_total_chars(candidate),
            dropped_error_message_count=dropped_error_message_count,
            truncated_for_gateway_budget=truncated_for_gateway_budget,
        )

    middle = rest[:idx_last_user]
    suffix = rest[idx_last_user:]

    while middle and messages_wire_total_chars(prefix + middle + suffix) > cap:
        middle.pop(0)
        truncated_for_gateway_budget = True

    candidate = prefix + middle + suffix
    if messages_wire_total_chars(candidate) > cap and _truncate_latest_user_wire_fit(candidate, cap):
        truncated_for_gateway_budget = True

    return candidate, HermesHttpContextBudgetResult(
        original_message_count=orig_count,
        final_message_count=len(candidate),
        original_char_count=orig_chars,
        final_char_count=messages_wire_total_chars(candidate),
        dropped_error_message_count=dropped_error_message_count,
        truncated_for_gateway_budget=truncated_for_gateway_budget,
    )
