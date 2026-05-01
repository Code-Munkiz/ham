"""Read-only Telegram inbound discovery from bounded Hermes transcript files."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.redaction import redact

MAX_INBOUND_ITEMS = 20
MAX_INBOUND_TEXT_CHARS = 500
MAX_TRANSCRIPT_SCAN_BYTES = 1_048_576

TelegramInboundStatus = Literal["completed", "blocked", "failed"]


class TelegramInboundItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inbound_id: str
    text: str
    author_ref: str = ""
    chat_ref: str = ""
    session_ref: str = ""
    created_at: str | None = None
    chat_type: str | None = None
    already_answered: bool = False
    repliable: bool = False
    reasons: list[str] = Field(default_factory=list)


class TelegramInboundDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    preview_kind: Literal["telegram_inbound"] = "telegram_inbound"
    status: TelegramInboundStatus = "blocked"
    execution_allowed: bool = False
    mutation_attempted: bool = False
    live_apply_available: bool = False
    inbound_count: int = 0
    items: list[TelegramInboundItem] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)


def discover_telegram_inbound_once(
    *,
    transcript_paths: list[Path] | None = None,
    max_items: int = MAX_INBOUND_ITEMS,
) -> TelegramInboundDiscoveryResult:
    paths = transcript_paths if transcript_paths is not None else _default_transcript_paths()
    if not paths:
        return _blocked("hermes_transcript_source_unavailable")

    warnings: list[str] = []
    items: list[TelegramInboundItem] = []
    saw_existing_source = False
    for path in paths:
        if len(items) >= max(1, min(max_items, MAX_INBOUND_ITEMS)):
            break
        if not path.is_file():
            continue
        saw_existing_source = True
        try:
            if path.stat().st_size > MAX_TRANSCRIPT_SCAN_BYTES:
                warnings.append("hermes_transcript_source_too_large")
                continue
            rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            warnings.append("hermes_transcript_source_unreadable")
            continue
        for line_no, line in enumerate(rows, start=1):
            if len(items) >= max(1, min(max_items, MAX_INBOUND_ITEMS)):
                break
            row = _parse_row(line)
            if row is None:
                if line.strip():
                    warnings.append("hermes_transcript_row_malformed")
                continue
            item = _item_from_row(row, path=path, line_no=line_no)
            if item is not None:
                items.append(item)

    if not saw_existing_source:
        return _blocked("hermes_transcript_source_unavailable")

    return TelegramInboundDiscoveryResult(
        status="completed",
        inbound_count=len(items),
        items=items,
        reasons=[],
        warnings=_dedupe(warnings),
        recommended_next_steps=_recommended_steps(items=items, warnings=warnings),
    )


def _default_transcript_paths() -> list[Path]:
    explicit = (os.environ.get("HAM_TELEGRAM_INBOUND_TRANSCRIPT_PATH") or "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    home = (os.environ.get("HAM_HERMES_HOME") or os.environ.get("HERMES_HOME") or "").strip()
    if not home:
        return []
    root = Path(home).expanduser()
    return [
        root / "telegram_sessions.jsonl",
        root / "sessions" / "telegram.jsonl",
        root / "transcripts" / "telegram.jsonl",
    ]


def _parse_row(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _item_from_row(row: dict[str, Any], *, path: Path, line_no: int) -> TelegramInboundItem | None:
    if not _is_telegram_row(row):
        return None
    if _role(row) != "user":
        return None
    text = _message_text(row)
    if not text:
        return None
    raw_session = _first_str(row, "session_id", "session", "conversation_id", "thread_id") or str(path)
    raw_author = _first_str(row, "author_id", "user_id", "from_id", "sender_id", "author") or ""
    raw_chat = _first_str(row, "chat_id", "room_id", "channel_id", "chat") or ""
    reasons: list[str] = []
    if not raw_chat:
        reasons.append("telegram_chat_ref_missing")
    if not raw_author:
        reasons.append("telegram_author_ref_missing")
    repliable = bool(raw_chat and raw_author)
    if not repliable:
        reasons.append("telegram_reply_target_unavailable")

    inbound_raw = _first_str(row, "message_id", "id", "event_id") or f"{path}:{line_no}"
    return TelegramInboundItem(
        inbound_id=_mask_ref(f"inbound:{raw_session}:{inbound_raw}"),
        text=_bounded_text(text),
        author_ref=_mask_ref(raw_author),
        chat_ref=_mask_ref(raw_chat),
        session_ref=_mask_ref(raw_session),
        created_at=_first_str(row, "created_at", "timestamp", "ts"),
        chat_type=_bounded_optional(_first_str(row, "chat_type", "type")),
        already_answered=_already_answered(row),
        repliable=repliable,
        reasons=_dedupe(reasons),
    )


def _is_telegram_row(row: dict[str, Any]) -> bool:
    source = _first_str(row, "source", "provider", "platform", "channel")
    if source and source.lower() == "telegram":
        return True
    return bool(row.get("telegram") is True)


def _role(row: dict[str, Any]) -> str:
    value = _first_str(row, "role", "message_role", "sender_role", "type")
    lowered = value.lower()
    if lowered in {"user", "human", "inbound"}:
        return "user"
    if lowered in {"assistant", "system", "tool"}:
        return lowered
    return lowered


def _message_text(row: dict[str, Any]) -> str:
    for key in ("text", "content", "message", "body"):
        value = row.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = value.get("text") or value.get("content")
            if isinstance(nested, str):
                return nested
    return ""


def _already_answered(row: dict[str, Any]) -> bool:
    for key in ("already_answered", "answered", "has_reply", "reply_sent"):
        value = row.get(key)
        if isinstance(value, bool):
            return value
    return False


def _first_str(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text[:256]
    return ""


def _mask_ref(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"configured:{digest}"


def _bounded_text(value: str) -> str:
    redacted = str(redact(value or "")).strip()
    return redacted[:MAX_INBOUND_TEXT_CHARS]


def _bounded_optional(value: str) -> str | None:
    text = str(redact(value or "")).strip()[:64]
    return text or None


def _blocked(reason: str) -> TelegramInboundDiscoveryResult:
    return TelegramInboundDiscoveryResult(
        status="blocked",
        inbound_count=0,
        items=[],
        reasons=[reason],
        recommended_next_steps=["Provide a safe Hermes Telegram transcript/session JSONL source, then preview again."],
    )


def _recommended_steps(*, items: list[TelegramInboundItem], warnings: list[str]) -> list[str]:
    if items:
        return ["Inbound preview loaded read-only. No reply was generated or sent."]
    if warnings:
        return ["Transcript source was found but no usable Telegram user messages were available."]
    return ["No Telegram inbound messages found in the configured transcript source."]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
