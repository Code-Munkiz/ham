"""Narrow HAM-owned Telegram one-shot sender for Social apply flows."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.ham.ham_x.redaction import redact
from src.ham.social_delivery_log import append_delivery_record, successful_delivery_exists

MAX_TELEGRAM_TEXT_CHARS = 700
TELEGRAM_EXECUTION_KIND = "social_telegram_message"
TELEGRAM_ACTION_TYPE = "message"

TelegramTargetKind = Literal["test_group", "home_channel"]
TelegramSendStatus = Literal["blocked", "sent", "failed", "duplicate"]
_RAW_NUMERIC_ID_RE = re.compile(r"(?<![A-Za-z])-?\d{6,}(?![A-Za-z])")


class TelegramSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_kind: TelegramTargetKind
    text: str = Field(default="", max_length=5000)
    proposal_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    persona_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=16, max_length=128)
    telegram_connected: bool = True


class TelegramSendResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: Literal["telegram"] = "telegram"
    status: TelegramSendStatus
    execution_allowed: bool = False
    mutation_attempted: bool = False
    target_kind: TelegramTargetKind | None = None
    target_ref: str | None = None
    provider_message_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, object] = Field(default_factory=dict)


class TelegramTransport(Protocol):
    def send_message(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        timeout_seconds: float,
    ) -> TelegramSendResult:
        ...


class TelegramBotApiTransport:
    """Minimal Telegram Bot API transport for a single plain-text send."""

    api_base = "https://api.telegram.org"

    def send_message(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        timeout_seconds: float,
    ) -> TelegramSendResult:
        url = f"{self.api_base}/bot{bot_token}/sendMessage"
        body = json.dumps(
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except TimeoutError:
            return TelegramSendResult(
                status="failed",
                execution_allowed=True,
                mutation_attempted=True,
                reasons=["provider_timeout_unknown_delivery"],
            )
        except (socket.timeout, urllib.error.URLError) as exc:
            reason = "provider_timeout_unknown_delivery" if isinstance(getattr(exc, "reason", None), socket.timeout) else "provider_send_failed"
            return TelegramSendResult(
                status="failed",
                execution_allowed=True,
                mutation_attempted=True,
                reasons=[reason],
                result={"diagnostic": _bounded_diagnostic(str(exc))},
            )
        except Exception as exc:  # pragma: no cover - defensive transport boundary
            return TelegramSendResult(
                status="failed",
                execution_allowed=True,
                mutation_attempted=True,
                reasons=["provider_send_failed"],
                result={"diagnostic": _bounded_diagnostic(str(exc))},
            )

        message_id = None
        if isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, dict) and result.get("message_id") is not None:
                message_id = str(result.get("message_id"))[:128]
        return TelegramSendResult(
            status="sent" if payload.get("ok") else "failed",
            execution_allowed=True,
            mutation_attempted=True,
            provider_message_id=message_id,
            reasons=[] if payload.get("ok") else ["provider_send_failed"],
        )


def mask_target_ref(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"configured:{digest}"


def resolve_telegram_target(target_kind: TelegramTargetKind) -> tuple[str | None, str]:
    if target_kind == "test_group":
        raw = (
            os.environ.get("TELEGRAM_TEST_GROUP")
            or os.environ.get("TELEGRAM_TEST_GROUP_ID")
            or os.environ.get("TELEGRAM_TEST_CHAT_ID")
            or ""
        ).strip()
    elif target_kind == "home_channel":
        raw = (os.environ.get("TELEGRAM_HOME_CHANNEL") or "").strip()
    else:
        return None, ""
    return (raw or None), mask_target_ref(raw)


def send_confirmed_telegram_message(
    request: TelegramSendRequest,
    *,
    transport: TelegramTransport | None = None,
    delivery_log_path: Path | None = None,
    timeout_seconds: float = 10.0,
    execution_kind: str = TELEGRAM_EXECUTION_KIND,
    action_type: str = TELEGRAM_ACTION_TYPE,
) -> TelegramSendResult:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id, target_ref = resolve_telegram_target(request.target_kind)
    preflight_reasons = _preflight_reasons(request, token=token, chat_id=chat_id)
    if preflight_reasons:
        return TelegramSendResult(
            status="blocked",
            target_kind=request.target_kind,
            target_ref=target_ref,
            reasons=preflight_reasons,
        )
    if successful_delivery_exists(idempotency_key=request.idempotency_key, path=delivery_log_path):
        return TelegramSendResult(
            status="duplicate",
            target_kind=request.target_kind,
            target_ref=target_ref,
            reasons=["duplicate_idempotency_key"],
        )

    sender = transport or TelegramBotApiTransport()
    result = sender.send_message(
        bot_token=token,
        chat_id=chat_id or "",
        text=request.text,
        timeout_seconds=timeout_seconds,
    )
    sanitized = TelegramSendResult(
        status=result.status,
        execution_allowed=True,
        mutation_attempted=True,
        target_kind=request.target_kind,
        target_ref=target_ref,
        provider_message_id=str(redact(result.provider_message_id))[:128] if result.provider_message_id else None,
        reasons=[str(redact(item))[:128] for item in result.reasons],
        warnings=[str(redact(item))[:128] for item in result.warnings],
        result=_safe_result(result.result),
    )
    append_delivery_record(
        {
            "provider_id": "telegram",
            "execution_kind": str(redact(execution_kind))[:128],
            "action_type": str(redact(action_type))[:64],
            "target_kind": request.target_kind,
            "target_ref": target_ref,
            "proposal_digest": request.proposal_digest,
            "persona_digest": request.persona_digest,
            "idempotency_key": request.idempotency_key,
            "provider_message_id": sanitized.provider_message_id,
            "status": sanitized.status,
            "execution_allowed": sanitized.execution_allowed,
            "mutation_attempted": sanitized.mutation_attempted,
        },
        path=delivery_log_path,
    )
    return sanitized


def _preflight_reasons(request: TelegramSendRequest, *, token: str, chat_id: str | None) -> list[str]:
    reasons: list[str] = []
    if not request.telegram_connected:
        reasons.append("telegram_not_connected")
    if not token:
        reasons.append("telegram_bot_token_missing")
    if not chat_id:
        reasons.append("telegram_target_missing")
    text = request.text.strip()
    if not text:
        reasons.append("telegram_message_empty")
    if len(text) > MAX_TELEGRAM_TEXT_CHARS:
        reasons.append("telegram_message_too_long")
    if _looks_like_media_or_attachment(text):
        reasons.append("telegram_plain_text_only")
    return reasons


def _looks_like_media_or_attachment(text: str) -> bool:
    lowered = text.lower()
    return "media:" in lowered or "attachment:" in lowered or "[attachment" in lowered


def _bounded_diagnostic(text: str) -> str:
    redacted = str(redact(text or "provider error"))
    redacted = _RAW_NUMERIC_ID_RE.sub("[REDACTED_ID]", redacted)
    return redacted[:240]


def _safe_result(data: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in list(data.items())[:20]:
        if isinstance(value, str):
            out[str(key)[:64]] = _bounded_diagnostic(value)
        elif isinstance(value, (bool, int, float)) or value is None:
            out[str(key)[:64]] = value
        else:
            out[str(key)[:64]] = _bounded_diagnostic(str(value))
    return out
