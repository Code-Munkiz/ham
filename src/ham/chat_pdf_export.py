"""Build audit-oriented PDF exports for persisted chat sessions (transcript only)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from src.ham.chat_user_content import try_parse_stored_v2, plain_text_for_operator
from src.ham.generated_media_store import is_safe_generated_media_id
from src.ham.pdf_export_sanitizer import redact_for_pdf_export

_LOG = logging.getLogger(__name__)

_EXCERPT_CHARS = 240


def _coerce_turn_content(content: Any) -> str:
    """Session stores should be strings, but coercion avoids PDF export crashes on bad rows."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (bytes, bytearray)):
        return bytes(content).decode("utf-8", errors="replace")
    if isinstance(content, dict):
        try:
            return json.dumps(content, separators=(",", ":"), ensure_ascii=False)
        except TypeError:
            return str(content)
    return str(content)


def _truncate_excerpt(text: str) -> str:
    t = " ".join((text or "").split())
    if len(t) > _EXCERPT_CHARS:
        return f"{t[:_EXCERPT_CHARS - 1]}…"
    return t


def _looks_like_generated_media_blob(obj: dict[str, Any]) -> bool:
    if isinstance(obj.get("generated_media_id"), str):
        return True
    h = obj.get("h")
    return h in {
        "ham_workspace_generated_media_v1",
        "ham_generated_media_v1",
        "generated_media",
    }


def _infer_generated_kind(obj: dict[str, Any]) -> str:
    mime = str(obj.get("mime_type") or obj.get("mime") or "").strip().lower()
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("image/"):
        return "image"
    mt = str(obj.get("media_type") or obj.get("type") or "").strip().lower()
    if mt in {"video", "image"}:
        return mt
    k = str(obj.get("kind") or obj.get("output_kind") or "").strip().lower()
    if k in {"video", "image", "generated_video", "generated_image"}:
        if "video" in k:
            return "video"
        if "image" in k:
            return "image"
    ot = obj.get("output_types")
    if isinstance(ot, list):
        blob = ",".join(str(x).lower() for x in ot)
        if "video" in blob:
            return "video"
        if "image" in blob:
            return "image"
    return "media"


def _try_generated_media_summary(raw: str) -> str | None:
    stripped = (raw or "").strip()
    if not stripped.startswith("{"):
        return None
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return "[generated media omitted]"
    if not _looks_like_generated_media_blob(obj):
        return None
    gid = obj.get("generated_media_id") or obj.get("artifact_id")
    if isinstance(gid, str) and is_safe_generated_media_id(gid):
        kind = _infer_generated_kind(obj)
        label = {"image": "image", "video": "video"}.get(kind, "media")
        excerpt = obj.get("prompt_excerpt") or obj.get("prompt_preview") or obj.get("prompt") or ""
        ex = _truncate_excerpt(str(excerpt)) if excerpt else "(no prompt excerpt)"
        lines = [
            f"Generated {label}: {ex}",
            f"Artifact: {gid}",
        ]
        return "\n".join(lines)
    if _looks_like_generated_media_blob(obj):
        return "[generated media omitted]"
    return None


def _minimal_fallback_pdf(session_id: str, created_at: str | None) -> bytes:
    """Minimal PDF via pdfgen_canvas so it stays independent of Paragraph / SimpleDocTemplate."""
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 9)
    _, page_h = letter
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    left = inch * 0.75
    y = page_h - inch * 0.75
    lines = [
        "HAM transcript export (fallback).",
        "",
        f"Session id: {session_id}",
        f"Session created: {created_at or '—'}",
        f"Exported (UTC): {stamp}",
        "",
        "[One or more turns could not be rendered into PDF markup.]",
    ]
    for ln in lines:
        c.drawString(left, y, ln[:260])
        y -= 12
        if y < inch * 0.75:
            c.showPage()
            y = page_h - inch * 0.75
            c.setFont("Helvetica", 9)
    c.save()
    return buf.getvalue()


def _utc_export_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_user_message_for_pdf(raw_content: str) -> str:
    """Operator-safe user text + attachment filenames (no ids, no extracted bodies)."""
    base = plain_text_for_operator(raw_content)
    v2 = try_parse_stored_v2(raw_content)
    if v2 is None:
        return base
    names: list[str] = []
    for a in v2.get("attachments") or []:
        if isinstance(a, dict):
            n = str(a.get("name") or "").strip()
            if n:
                names.append(n)
    if not names:
        return base
    safe_names = [redact_for_pdf_export(n) for n in names]
    extra = "Attachments referenced (names only): " + ", ".join(safe_names)
    if base.strip():
        return f"{base}\n{extra}"
    return extra


def _format_turn_body(role: str, content: str) -> str:
    if role == "user":
        body = _format_user_message_for_pdf(content)
    else:
        text = content or ""
        summary = _try_generated_media_summary(text)
        body = summary if summary is not None else text
    return redact_for_pdf_export(body)


def _paragraph_from_text(text: str, style: ParagraphStyle) -> Paragraph:
    """ReportLab Paragraph with newlines as <br/>; resilient to rare markup-parse failures."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    frag = escape(raw).replace("\n", "<br/>")
    try:
        return Paragraph(frag, style)
    except Exception as exc:
        try:
            flat = "".join(ch for ch in raw if ord(ch) >= 32 or ch in "\n\t")
            frag2 = escape(flat[:200_000]).replace("\n", "<br/>")
            return Paragraph(frag2, style)
        except Exception:
            _LOG.warning("PDF paragraph markup failed after fallback (%s)", exc)
            omit = escape("[Turn text omitted due to PDF rendering limits.]").replace("\n", "<br/>")
            return Paragraph(omit, style)


def render_chat_transcript_pdf_bytes(
    *,
    session_id: str,
    created_at: str | None,
    turns: list[tuple[str, Any]],
) -> bytes:
    """
    ``turns`` — ``(role, content)`` in order; ``content`` is persisted session text
    (may include ham_chat_user_v2 JSON for user turns).

    Turn bodies are coerced to ``str`` at export time so a bad row cannot crash ``escape()`` /
    redaction helpers.
    """
    norm_turns: list[tuple[str, str]] = [(role, _coerce_turn_content(c)) for role, c in turns]
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=inch * 0.75,
        leftMargin=inch * 0.75,
        topMargin=inch * 0.75,
        bottomMargin=inch * 0.75,
        title="HAM chat transcript",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ExpTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=12,
    )
    meta_style = ParagraphStyle(
        "ExpMeta",
        parent=styles["Normal"],
        fontSize=9,
        textColor="#444444",
        spaceAfter=6,
    )
    role_style = ParagraphStyle(
        "ExpRole",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "ExpBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        spaceAfter=8,
    )
    footer_style = ParagraphStyle(
        "ExpFoot",
        parent=styles["Normal"],
        fontSize=8,
        textColor="#666666",
        spaceBefore=18,
    )

    story: list = []
    story.append(Paragraph("HAM — Chat transcript export", title_style))
    story.append(
        _paragraph_from_text(
            f"Session id: {session_id}\n"
            f"Session created: {created_at or '—'}\n"
            f"Exported (UTC): {_utc_export_stamp()}",
            meta_style,
        ),
    )
    story.append(Spacer(1, 0.1 * inch))

    for role, content in norm_turns:
        r = (role or "").strip().lower()
        label = (
            "User"
            if r == "user"
            else "Assistant"
            if r == "assistant"
            else ((role or "message").strip().title() or "Message")
        )
        story.append(Paragraph(escape(label), role_style))
        body = _format_turn_body(r, content)
        story.append(_paragraph_from_text(body, body_style))

    story.append(
        _paragraph_from_text(
            "Generated by HAM from stored transcript. "
            "Does not include raw attachment bytes or storage locations.",
            footer_style,
        ),
    )
    try:
        doc.build(story)
    except Exception:
        _LOG.exception("chat transcript PDF export failed — returning minimal fallback")
        return _minimal_fallback_pdf(session_id, created_at)
    return buf.getvalue()
