"""
Structured workspace chat user content (screenshots / multimodal).

Wire format (persisted in chat session ``content`` string)::

    {"h": "ham_chat_user_v1", "text": "...", "images": [{"name", "mime", "data_url"}]}

The browser sends the same object as JSON for ``ChatMessageIn.content``; the API
normalizes to a single JSON string for storage. OpenRouter receives OpenAI-style
``content`` parts; HTTP/mock gateways may not forward image bytes (see
``to_llm_message_content``).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

HAM_CHAT_USER_V1 = "ham_chat_user_v1"

_MAX_MESSAGE_JSON_BYTES = 1_200_000
_MAX_IMAGES = 8

_ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp"})
_RE_DATA_URL = re.compile(
    r"^data:(image/(?:png|jpeg|jpg|webp));base64,([A-Za-z0-9+/=\s]+)\s*$",
    re.IGNORECASE,
)
_CANON_MIME = {"image/png", "image/jpeg", "image/webp"}

# Normalize mime variants
def _norm_mime(m: str) -> str:
    x = (m or "").strip().lower()
    if x == "image/jpg":
        return "image/jpeg"
    return x


def _data_url_bytes(data_url: str) -> int:
    """Rough byte size of base64 payload (same heuristic as the frontend)."""
    if "base64," not in data_url:
        return len(data_url)
    b64 = data_url.split("base64,", 1)[1].replace("\n", "").replace("\r", "")
    return int(len(b64) * 0.75)


def _validate_v1(doc: dict[str, Any]) -> dict[str, Any]:
    if doc.get("h") != HAM_CHAT_USER_V1:
        raise ValueError("Invalid structured user message (missing ham_chat_user_v1 header).")
    text = doc.get("text")
    if text is not None and not isinstance(text, str):
        raise ValueError("Invalid user message: text must be a string.")
    t = (text or "").strip()
    images_raw = doc.get("images")
    if not isinstance(images_raw, list):
        raise ValueError("Invalid user message: images must be a list.")
    if len(images_raw) > _MAX_IMAGES:
        raise ValueError(f"At most {_MAX_IMAGES} images are allowed per message.")
    out_images: list[dict[str, str]] = []
    for i, it in enumerate(images_raw):
        if not isinstance(it, dict):
            raise ValueError("Invalid user message: each image must be an object.")
        name = str(it.get("name") or f"image-{i + 1}").strip() or f"image-{i + 1}"
        filed = _norm_mime(str(it.get("mime") or ""))
        if filed not in _ALLOWED_MIME:
            raise ValueError(
                f"Unsupported or invalid image type: {filed!r} (use image/png, image/jpeg, or image/webp).",
            )
        data_url = str(it.get("data_url") or "").strip()
        m = _RE_DATA_URL.match(re.sub(r"\s+", "", data_url))
        if not m:
            raise ValueError("Invalid image data_url (expected a base64 data: URL for png, jpeg, or webp).")
        from_url = _norm_mime(m.group(1))
        if from_url not in _ALLOWED_MIME:
            raise ValueError("data: URL is not an allowed image type.")
        f2 = "image/jpeg" if filed in {"image/jpg", "image/jpeg"} else filed
        u2 = "image/jpeg" if from_url in {"image/jpg", "image/jpeg"} else from_url
        if f2 != u2:
            raise ValueError("Image `mime` and data: URL media type must match.")
        try:
            cap = int((os.environ.get("HAM_CHAT_IMAGE_MAX_BYTES") or str(500 * 1024)).strip())
        except ValueError:
            cap = 500 * 1024
        if _data_url_bytes(data_url) > cap:
            raise ValueError("Image is too large for chat (increase HAM_CHAT_IMAGE_MAX_BYTES on server if needed).")
        stored_m = f2
        if stored_m not in _CANON_MIME:
            raise ValueError("Internal image type normalization error.")
        out_images.append(
            {
                "name": name[:240],
                "mime": stored_m,
                "data_url": data_url,
            }
        )
    if not t and not out_images:
        raise ValueError("User message is empty (add text and/or a screenshot).")
    return {"h": HAM_CHAT_USER_V1, "text": t, "images": out_images}


def try_parse_stored_v1(stored: str) -> dict[str, Any] | None:
    s = (stored or "").strip()
    if not s.startswith("{"):
        return None
    try:
        doc = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(doc, dict) or doc.get("h") != HAM_CHAT_USER_V1:
        return None
    return doc  # not fully validated (already validated at write)


def normalize_user_incoming_to_stored(
    content: str | dict[str, Any] | list[Any],
) -> str:
    """Normalize request ``content`` to a single string suitable for session storage."""
    if isinstance(content, str):
        s = content.strip()
        if not s:
            raise ValueError("User message is empty.")
        if s.startswith("{"):
            try:
                doc = json.loads(s)
            except json.JSONDecodeError:
                if len(s) > 100_000:
                    raise ValueError("Message is too long.") from None
                return s
            if isinstance(doc, dict) and doc.get("h") == HAM_CHAT_USER_V1:
                v = _validate_v1(doc)
                out = json.dumps(v, separators=(",", ":"), ensure_ascii=False)
                if len(out.encode("utf-8")) > _MAX_MESSAGE_JSON_BYTES:
                    raise ValueError("Message with attachments is too large.")
                return out
            # Valid JSON but not our structured message — store as literal user text.
            if len(s) > 100_000:
                raise ValueError("Message is too long.")
            return s
        if len(s) > 100_000:
            raise ValueError("Message is too long.")
        return s
    if isinstance(content, dict):
        v = _validate_v1(content)
        out = json.dumps(v, separators=(",", ":"), ensure_ascii=False)
        if len(out.encode("utf-8")) > _MAX_MESSAGE_JSON_BYTES:
            raise ValueError("Message with attachments is too large.")
        return out
    raise ValueError("Invalid user message content type.")


def plain_text_for_operator(stored: str) -> str:
    """Text-only / safe summary for the operator and previews."""
    v = try_parse_stored_v1(stored)
    if v is None:
        return stored
    t = (v.get("text") or "").strip()
    n = len(v.get("images") or [])
    if n and t:
        return f"{t}\n[User attached {n} image(s) in the dashboard.]".strip()
    if n:
        return f"[User attached {n} image(s) in the dashboard.]"
    return t or ""


def _gateway_mode() -> str:
    raw = (os.environ.get("HERMES_GATEWAY_MODE") or "").strip().lower()
    if raw in {"mock", "openrouter", "http"}:
        return raw
    base = (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip()
    return "http" if base else "mock"


def _http_vision_flag() -> bool:
    v = (os.environ.get("HAM_CHAT_HTTP_VISION", "") or "").strip().lower()
    return v in {"1", "true", "yes"}


def _openrouter_vision_default() -> bool:
    v = (os.environ.get("HAM_CHAT_VISION_FORWARD", "1") or "").strip().lower()
    return v not in {"0", "false", "no"}


def to_llm_message_content(stored: str) -> str | list[dict[str, Any]]:
    """
    Convert stored user message to ``content`` for the OpenAI-compatible gateway
    (string, or a list of text/image parts).
    """
    v = try_parse_stored_v1(stored)
    if v is None:
        return stored

    text = (v.get("text") or "").strip()
    images: list[dict[str, str]] = [x for x in (v.get("images") or []) if isinstance(x, dict)]

    mode = _gateway_mode()
    forward_vision = (mode == "openrouter" and _openrouter_vision_default()) or (
        mode == "http" and _http_vision_flag()
    )

    if not forward_vision or not images:
        if not text and not images:
            return ""
        if images and not text:
            return (
                "[User attached a screenshot in Ham Workspace Chat, but this chat runtime does not forward "
                "image bytes to the model. Enable OpenRouter (HERMES_GATEWAY_MODE=openrouter) with "
                "HAM_CHAT_VISION_FORWARD=1, or for HTTP gateways set HAM_CHAT_HTTP_VISION=1 if the upstream "
                "supports vision.]"
            )
        if images:
            return (
                f"{text}\n\n[User attached a screenshot. This deployment is not currently forwarding image "
                f"bytes to the model; describe limitations honestly — you cannot see the image pixels.]"
            ).strip()
        return text

    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    for im in images:
        url = str(im.get("data_url") or "")
        if url:
            parts.append({"type": "image_url", "image_url": {"url": url}})
    if not parts:
        return ""
    if len(parts) == 1 and parts[0].get("type") == "text":
        return str(parts[0].get("text") or "")
    return parts


def has_screenshot_in_stored(stored: str) -> bool:
    v = try_parse_stored_v1(stored)
    if v is None:
        return False
    return bool(v.get("images"))


def vision_system_suffix() -> str:
    return (
        "\n**Vision (workspace chat):** When the user message includes screenshot image parts, "
        "read them and answer based on what is visible. If only text reached you, say so honestly."
    )
