"""
Structured workspace chat user content (screenshots / multimodal).

Wire formats (persisted in chat session ``content`` string)::

    {"h": "ham_chat_user_v1", "text": "...", "images": [{"name", "mime", "data_url"}]}

    {"h": "ham_chat_user_v2", "text": "...", "attachments": [{"id", "name", "mime", "kind"}]}

v2 uses opaque ``attachment`` ids and server-side blob storage; v1 embeds
base64 in Firestore. OpenRouter and HTTP Hermes receive OpenAI-style ``content`` parts (including
``image_url`` data URLs resolved server-side for v2). Vision forwarding honors
``HAM_CHAT_VISION_FORWARD`` (default on for ``openrouter`` and ``http``), ``HAM_CHAT_VISION_MODE`` (``auto`` vs ``off``),
and optional caps ``HAM_CHAT_VISION_MAX_IMAGES`` / ``HAM_CHAT_VISION_MAX_IMAGE_BYTES``.
Mock mode does not forward.
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Literal

from src.ham.chat_attachment_store import (
    CHAT_UPLOAD_ALLOWED_MIME,
    get_chat_attachment_store,
    is_safe_attachment_id,
)
from src.ham.chat_document_extraction import (
    DocumentExtractionResult,
    build_document_llm_sections,
    extract_document_bytes,
)

HAM_CHAT_USER_V1 = "ham_chat_user_v1"
HAM_CHAT_USER_V2 = "ham_chat_user_v2"

_MAX_MESSAGE_JSON_BYTES = 1_200_000
_MAX_IMAGES = 5

_ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp"})
_RE_DATA_URL = re.compile(
    r"^data:(image/(?:png|jpeg|jpg|webp));base64,([A-Za-z0-9+/=\s]+)\s*$",
    re.IGNORECASE,
)
_CANON_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif"}

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


def _check_attachment_owner(
    owner_in_meta: str,
    current_user: str | None,
) -> bool:
    """
    If the uploaded file was tagged with a Clerk user id, the same user must
    reference it in chat. If ``owner_in_meta`` is empty (local dev / no auth),
    allow any in-process user (id must still exist on disk).
    """
    o = (owner_in_meta or "").strip()
    if not o:
        return True
    c = (current_user or "").strip()
    return bool(c) and c == o


def _validate_v2(
    doc: dict[str, Any],
    *,
    attachment_user_id: str | None,
) -> dict[str, Any]:
    if doc.get("h") != HAM_CHAT_USER_V2:
        raise ValueError("Invalid structured user message (missing ham_chat_user_v2 header).")
    text = doc.get("text")
    if text is not None and not isinstance(text, str):
        raise ValueError("Invalid user message: text must be a string.")
    t = (text or "").strip()
    at_raw = doc.get("attachments")
    if not isinstance(at_raw, list) or not at_raw:
        raise ValueError("Invalid user message: attachments must be a non-empty list for v2.")
    if len(at_raw) > _MAX_IMAGES:
        raise ValueError(f"At most {_MAX_IMAGES} attachments are allowed per message.")
    store = get_chat_attachment_store()
    out: list[dict[str, str]] = []
    for i, it in enumerate(at_raw):
        if not isinstance(it, dict):
            raise ValueError("Invalid user message: each attachment must be an object.")
        aid = str(it.get("id") or "").strip()
        if not is_safe_attachment_id(aid):
            raise ValueError("Invalid attachment id.")
        name = str(it.get("name") or f"file-{i + 1}").strip() or f"file-{i + 1}"
        rec = store.get_meta(aid)
        if rec is None:
            raise ValueError("Unknown or expired attachment id (re-upload the file).")
        if not _check_attachment_owner(rec.owner_key, attachment_user_id):
            raise ValueError("Attachment is not available for this user.")
        filed = _norm_mime(str(it.get("mime") or rec.mime))
        if filed not in CHAT_UPLOAD_ALLOWED_MIME:
            raise ValueError(
                f"Unsupported attachment type: {filed!r} (allowed types are workspace upload MIME set).",
            )
        if _norm_mime(rec.mime) != filed:
            raise ValueError("Attachment `mime` does not match the uploaded file.")
        expect_kind: Literal["image", "file"] = "image" if filed.startswith("image/") else "file"
        if rec.kind not in ("image", "file"):
            raise ValueError("Stored attachment is corrupted (invalid kind).")
        if rec.kind != expect_kind:
            raise ValueError("Attachment `mime` and stored kind do not match.")
        out.append(
            {
                "id": aid,
                "name": name[:240],
                "mime": filed,
                "kind": expect_kind,
            }
        )
    if not t and not out:
        raise ValueError("User message is empty (add text and/or attachments).")
    return {"h": HAM_CHAT_USER_V2, "text": t, "attachments": out}


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


def try_parse_stored_v2(stored: str) -> dict[str, Any] | None:
    s = (stored or "").strip()
    if not s.startswith("{"):
        return None
    try:
        doc = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(doc, dict) or doc.get("h") != HAM_CHAT_USER_V2:
        return None
    return doc


def _dump_user_json(doc: dict[str, Any]) -> str:
    out = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
    if len(out.encode("utf-8")) > _MAX_MESSAGE_JSON_BYTES:
        raise ValueError("Message with attachments is too large.")
    return out


def normalize_user_incoming_to_stored(
    content: str | dict[str, Any] | list[Any],
    *,
    attachment_user_id: str | None = None,
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
                return _dump_user_json(v)
            if isinstance(doc, dict) and doc.get("h") == HAM_CHAT_USER_V2:
                v = _validate_v2(doc, attachment_user_id=attachment_user_id)
                return _dump_user_json(v)
            # Valid JSON but not our structured message — store as literal user text.
            if len(s) > 100_000:
                raise ValueError("Message is too long.")
            return s
        if len(s) > 100_000:
            raise ValueError("Message is too long.")
        return s
    if isinstance(content, dict):
        h = content.get("h")
        if h == HAM_CHAT_USER_V1:
            v = _validate_v1(content)
            return _dump_user_json(v)
        if h == HAM_CHAT_USER_V2:
            v = _validate_v2(content, attachment_user_id=attachment_user_id)
            return _dump_user_json(v)
        raise ValueError("Invalid user message: expected ham_chat_user_v1 or ham_chat_user_v2.")
    raise ValueError("Invalid user message content type.")


def plain_text_for_operator(stored: str) -> str:
    """Text-only / safe summary for the operator and previews.

    Must not load attachment bytes or include extracted document bodies — only
    user-typed text plus attachment counts — so session/API summaries never
    leak file contents.
    """
    v2 = try_parse_stored_v2(stored)
    if v2 is not None:
        t = (v2.get("text") or "").strip()
        n = len(v2.get("attachments") or [])
        img = sum(1 for x in (v2.get("attachments") or []) if isinstance(x, dict) and x.get("kind") == "image")
        if n and t:
            return f"{t}\n[User attached {n} file(s) in the dashboard ({img} image(s)).]".strip()
        if n:
            return f"[User attached {n} file(s) in the dashboard ({img} image(s)).]"
        return t or ""
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


def _vision_policy_mode() -> str:
    """``HAM_CHAT_VISION_MODE`` — ``auto`` (default) or ``off`` (never forward pixels)."""
    raw = (os.environ.get("HAM_CHAT_VISION_MODE") or "auto").strip().lower()
    return "off" if raw == "off" else "auto"


def _positive_int_env(name: str, default: int, *, upper: int = 128) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return max(0, min(upper, v))


def _gateway_vision_forward_enabled() -> bool:
    """
    Emit multimodal ``image_url`` parts toward OpenRouter or the HTTP Hermes gateway.

    Default: enabled (same as legacy OpenRouter behavior). Disable with
    ``HAM_CHAT_VISION_FORWARD`` = ``0`` / ``false`` / ``no`` for gateways that
    reject multimodal payloads, or ``HAM_CHAT_VISION_MODE`` = ``off``.
    """
    if _vision_policy_mode() == "off":
        return False
    v = (os.environ.get("HAM_CHAT_VISION_FORWARD", "1") or "").strip().lower()
    return v not in {"0", "false", "no"}


def _vision_forward_max_images() -> int:
    """``HAM_CHAT_VISION_MAX_IMAGES`` — forwarded image parts ceiling (multimodal only)."""
    return max(1, _positive_int_env("HAM_CHAT_VISION_MAX_IMAGES", 1, upper=64))


def _vision_forward_max_image_bytes() -> int:
    """``HAM_CHAT_VISION_MAX_IMAGE_BYTES`` — per-image raw bytes forwarded (default 1 MiB)."""
    return max(4_096, _positive_int_env("HAM_CHAT_VISION_MAX_IMAGE_BYTES", 1_048_576, upper=48 * 1024 * 1024))


def _no_forward_banner_phrase() -> str:
    return "HAM_CHAT_VISION_MODE is off" if _vision_policy_mode() == "off" else "HAM_CHAT_VISION_FORWARD=0"


def _llm_vision_honest_no_forward(*, has_images: bool, text: str) -> str:
    if not has_images and not text:
        return ""
    banner = _no_forward_banner_phrase()
    if has_images and not text:
        return (
            f"[User attached image(s). Vision forwarding is disabled ({banner}), so image "
            "pixels are not sent to the model — answer only from visible text markers.]"
        )
    if has_images:
        return (
            f"{text}\n\n[User attached image(s). Vision forwarding is disabled ({banner}); "
            "image pixels are not sent — you cannot see the image. Answer honestly and suggest adjusting "
            "vision settings or switching to a vision-capable gateway path.]"
        ).strip()
    return text


def to_llm_message_content(
    stored: str,
    *,
    attachment_user_id: str | None = None,
) -> str | list[dict[str, Any]]:
    """
    Convert stored user message to ``content`` for the OpenAI-compatible gateway
    (string, or a list of text/image parts).

    When ``attachment_user_id`` is set (Clerk user id from the active chat caller),
    v2 attachment blobs are only loaded if each attachment's stored ``owner_key``
    is empty (local dev) or matches that user. When ``attachment_user_id`` is
    ``None`` and an attachment has a non-empty owner, bytes are not loaded (cannot
    verify the reader).
    """
    v2 = try_parse_stored_v2(stored)
    if v2 is not None:
        return _to_llm_message_content_v2(v2, attachment_user_id=attachment_user_id)
    v = try_parse_stored_v1(stored)
    if v is None:
        return stored

    text = (v.get("text") or "").strip()
    images: list[dict[str, str]] = [x for x in (v.get("images") or []) if isinstance(x, dict)]

    mode = _gateway_mode()
    forward_vision = mode in {"openrouter", "http"} and _gateway_vision_forward_enabled()

    if not forward_vision or not images:
        return _llm_vision_honest_no_forward(has_images=bool(images), text=text)

    max_fwd = _vision_forward_max_images()
    max_raw = _vision_forward_max_image_bytes()
    forwarded = 0
    notes: list[str] = []
    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    for im in images:
        url = str(im.get("data_url") or "")
        sz = _data_url_bytes(url) if url else 0
        name = str(im.get("name") or "").strip() or "(image)"
        if forwarded >= max_fwd:
            notes.append(f"{name}: not forwarded (limit {max_fwd} image(s) per turn).")
            continue
        if sz > max_raw:
            notes.append(f"{name}: not forwarded (~{sz} bytes; max forwarded size is {max_raw} bytes on this deployment).")
            continue
        if url:
            parts.append({"type": "image_url", "image_url": {"url": url}})
            forwarded += 1

    merged_notes = "; ".join(notes)
    only_text_so_far = len(parts) == 1 and parts[0].get("type") == "text"
    if merged_notes and only_text_so_far:
        base = str(parts[0].get("text") or "")
        appendix = (
            f"\n\n[Attachment note: {' '.join(notes)} "
            "The user still uploaded these in the dashboard; answer from visible text markers and be honest "
            "that image pixels beyond the forwarded allowance were withheld.]"
        )
        merged = (base + appendix).strip()
        return merged if merged else appendix.strip()
    if merged_notes:
        suffix = (
            "[Attachment note] "
            + merged_notes
            + " Uploaded images beyond this limit are withheld from pixels sent to this model."
        )
        tx = "".join(str(p.get("text") or "") for p in parts if p.get("type") == "text").strip()
        tail = suffix if not tx else f"{tx}\n\n{suffix}"
        img_only = [
            x for x in parts if isinstance(x, dict) and str(x.get("type") or "") == "image_url"
        ]
        if not img_only:
            return tail
        rebuilt: list[dict[str, Any]] = []
        rebuilt.append({"type": "text", "text": tail.strip()})
        rebuilt.extend(img_only)
        return rebuilt
    if not parts:
        return ""
    if len(parts) == 1 and parts[0].get("type") == "text":
        return str(parts[0].get("text") or "")
    return parts


def _bytes_to_image_data_url(mime: str, raw: bytes) -> str:
    b64 = base64.standard_b64encode(raw).decode("ascii")
    m = _norm_mime(mime)
    if m not in _CANON_MIME:
        m = "image/png"
    return f"data:{m};base64,{b64}"


def _to_llm_message_content_v2(
    v2: dict[str, Any],
    *,
    attachment_user_id: str | None = None,
) -> str | list[dict[str, Any]]:
    base_text = (v2.get("text") or "").strip()
    ats = [x for x in (v2.get("attachments") or []) if isinstance(x, dict)]
    store = get_chat_attachment_store()
    missing_blocks: list[str] = []
    file_results: list[DocumentExtractionResult] = []
    image_rows: list[tuple[bytes, str, str]] = []
    for a in ats:
        aid = str(a.get("id") or "")
        if not is_safe_attachment_id(aid):
            continue
        meta = store.get_meta(aid)
        if meta is None:
            name = str(a.get("name") or "attachment")
            missing_blocks.append(f"[Attachment missing on server: {name}]")
            continue
        if not _check_attachment_owner(meta.owner_key, attachment_user_id):
            name = str(a.get("name") or "attachment")
            missing_blocks.append(f"[Attachment not available for this session: {name}]")
            continue
        got = store.get(aid)
        if got is None:
            name = str(a.get("name") or "attachment")
            missing_blocks.append(f"[Attachment missing on server: {name}]")
            continue
        raw, rec = got
        m = _norm_mime(rec.mime)
        if rec.kind == "file":
            disp = str(a.get("name") or rec.filename).strip() or rec.filename
            file_results.append(
                extract_document_bytes(filename=disp, mime=m, raw=raw),
            )
        elif rec.kind == "image" or m.startswith("image/"):
            disp = str(a.get("name") or rec.filename).strip() or "(image)"
            image_rows.append((raw, rec.mime, disp))

    file_text_blocks = build_document_llm_sections(file_results)
    file_text_blocks = missing_blocks + file_text_blocks

    text = base_text
    if file_text_blocks:
        merged = "\n".join(file_text_blocks).strip()
        text = f"{text}\n\n{merged}".strip() if text else merged

    mode = _gateway_mode()
    forward_vision = mode in {"openrouter", "http"} and _gateway_vision_forward_enabled()

    if not image_rows:
        return text or ""

    if not forward_vision:
        return _llm_vision_honest_no_forward(has_images=True, text=text)

    max_fwd = _vision_forward_max_images()
    max_raw = _vision_forward_max_image_bytes()
    notes: list[str] = []
    forwarded_urls: list[str] = []
    for raw, mime, fname in image_rows:
        if len(forwarded_urls) >= max_fwd:
            notes.append(f"{fname}: not forwarded (limit {max_fwd} image(s) per turn).")
            continue
        if len(raw) > max_raw:
            notes.append(
                f"{fname}: not forwarded ({len(raw)} bytes uploaded; forwarded cap is {max_raw} bytes on this deployment)."
            )
            continue
        forwarded_urls.append(_bytes_to_image_data_url(mime, raw))

    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    for url in forwarded_urls:
        parts.append({"type": "image_url", "image_url": {"url": url}})

    merged_notes = "; ".join(notes)
    only_text_so_far = len(parts) == 1 and parts[0].get("type") == "text"
    if merged_notes and only_text_so_far:
        base = str(parts[0].get("text") or "")
        appendix = (
            f"\n\n[Attachment note: {' '.join(notes)} "
            "The user still uploaded these in the dashboard; answer from visible text markers and be honest "
            "that image pixels beyond the forwarded allowance were withheld.]"
        )
        merged = (base + appendix).strip()
        return merged if merged else appendix.strip()
    if merged_notes:
        suffix = (
            "[Attachment note] "
            + merged_notes
            + " Uploaded images beyond this limit are withheld from pixels sent to this model."
        )
        tx = "".join(str(p.get("text") or "") for p in parts if p.get("type") == "text").strip()
        tail = suffix if not tx else f"{tx}\n\n{suffix}"
        img_only = [x for x in parts if isinstance(x, dict) and str(x.get("type") or "") == "image_url"]
        if not img_only:
            return tail.strip()
        rebuilt: list[dict[str, Any]] = [{"type": "text", "text": tail.strip()}]
        rebuilt.extend(img_only)
        return rebuilt
    if not parts:
        return ""
    if len(parts) == 1 and parts[0].get("type") == "text":
        return str(parts[0].get("text") or "")
    return parts


def has_screenshot_in_stored(stored: str) -> bool:
    v2 = try_parse_stored_v2(stored)
    if v2 is not None:
        return any(
            isinstance(x, dict) and str(x.get("kind") or "") == "image" for x in (v2.get("attachments") or [])
        )
    v = try_parse_stored_v1(stored)
    if v is None:
        return False
    return bool(v.get("images"))


def vision_system_suffix() -> str:
    return (
        "\n**Vision (workspace chat):** When the user message includes screenshot image parts, "
        "read them and answer based on what is visible. If only text reached you, say so honestly."
    )
