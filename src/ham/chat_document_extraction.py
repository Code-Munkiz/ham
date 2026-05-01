"""
Server-side document text extraction for workspace chat attachments.

Extracted text is used only when assembling LLM message content
(``to_llm_message_content``); it must not be persisted in session storage,
returned in attachment APIs, or logged in full.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

MAX_EXTRACTED_CHARS_PER_FILE = 30_000
MAX_EXTRACTED_CHARS_PER_MESSAGE = 60_000
MAX_PDF_PAGES = 25
MAX_DOCX_PARAGRAPHS = 2_000
MAX_DOCX_TABLES = 200

ExtractionStatus = Literal["extracted", "truncated", "unsupported", "failed", "empty"]


@dataclass(frozen=True)
class DocumentExtractionResult:
    filename: str
    mime: str
    status: ExtractionStatus
    text: str
    truncated: bool
    error_reason: str | None


def _cap_body(body: str, limit: int) -> tuple[str, bool]:
    if len(body) <= limit:
        return body, False
    return body[:limit], True


def _decode_plain_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _extract_pdf(raw: bytes) -> tuple[str, ExtractionStatus, bool, str | None]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "failed", False, "pdf_library_unavailable"

    try:
        reader = PdfReader(BytesIO(raw))
    except Exception:
        return "", "failed", False, "invalid_pdf"

    parts: list[str] = []
    page_count = min(len(reader.pages), MAX_PDF_PAGES)
    truncated_pages = len(reader.pages) > MAX_PDF_PAGES
    for i in range(page_count):
        try:
            page = reader.pages[i]
            t = (page.extract_text() or "").strip()
        except Exception:
            continue
        if t:
            parts.append(t)
    merged = "\n\n".join(parts).strip()
    if not merged:
        return "", "empty", False, None
    capped, cut = _cap_body(merged, MAX_EXTRACTED_CHARS_PER_FILE)
    st: ExtractionStatus
    if cut or truncated_pages:
        st = "truncated"
    else:
        st = "extracted"
    return capped, st, cut or truncated_pages, None


def _extract_docx(raw: bytes) -> tuple[str, ExtractionStatus, bool, str | None]:
    try:
        from docx import Document
    except ImportError:
        return "", "failed", False, "docx_library_unavailable"

    try:
        doc = Document(BytesIO(raw))
    except Exception:
        return "", "failed", False, "invalid_docx"

    lines: list[str] = []
    char_budget = MAX_EXTRACTED_CHARS_PER_FILE
    truncated = False

    for pi, p in enumerate(doc.paragraphs):
        if pi >= MAX_DOCX_PARAGRAPHS:
            truncated = True
            break
        t = (p.text or "").strip()
        if not t:
            continue
        if len(t) > char_budget:
            lines.append(t[:char_budget])
            char_budget = 0
            truncated = True
            break
        lines.append(t)
        char_budget -= len(t) + 1
        if char_budget <= 0:
            truncated = True
            break

    if char_budget > 0:
        for ti, table in enumerate(doc.tables):
            if ti >= MAX_DOCX_TABLES:
                truncated = True
                break
            for row in table.rows:
                for cell in row.cells:
                    t = (cell.text or "").strip()
                    if not t:
                        continue
                    if len(t) > char_budget:
                        lines.append(t[:char_budget])
                        char_budget = 0
                        truncated = True
                        break
                    lines.append(t)
                    char_budget -= len(t) + 1
                    if char_budget <= 0:
                        truncated = True
                        break
                if char_budget <= 0:
                    break
            if char_budget <= 0:
                break

    merged = "\n".join(lines).strip()
    if not merged:
        return "", "empty", False, None
    capped, cut = _cap_body(merged, MAX_EXTRACTED_CHARS_PER_FILE)
    st: ExtractionStatus = "truncated" if (cut or truncated) else "extracted"
    return capped, st, cut or truncated, None


def extract_document_bytes(*, filename: str, mime: str, raw: bytes) -> DocumentExtractionResult:
    """
    Best-effort extraction. Never raises; failures become ``failed`` / ``unsupported`` results.
    """
    fn = (filename or "").strip() or "attachment"
    m = (mime or "").strip().lower()
    if m == "image/jpg":
        m = "image/jpeg"

    if m in ("text/plain", "text/markdown"):
        body = _decode_plain_text(raw)
        capped, cut = _cap_body(body, MAX_EXTRACTED_CHARS_PER_FILE)
        if not capped.strip():
            return DocumentExtractionResult(
                filename=fn,
                mime=m,
                status="empty",
                text="",
                truncated=False,
                error_reason=None,
            )
        st: ExtractionStatus = "truncated" if cut else "extracted"
        return DocumentExtractionResult(
            filename=fn,
            mime=m,
            status=st,
            text=capped,
            truncated=cut,
            error_reason=None,
        )

    if m == "application/pdf":
        text, st, trunc, err = _extract_pdf(raw)
        return DocumentExtractionResult(
            filename=fn,
            mime=m,
            status=st,
            text=text,
            truncated=trunc,
            error_reason=err,
        )

    if m == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        text, st, trunc, err = _extract_docx(raw)
        return DocumentExtractionResult(
            filename=fn,
            mime=m,
            status=st,
            text=text,
            truncated=trunc,
            error_reason=err,
        )

    if m == "application/msword":
        return DocumentExtractionResult(
            filename=fn,
            mime=m,
            status="unsupported",
            text="",
            truncated=False,
            error_reason=None,
        )

    return DocumentExtractionResult(
        filename=fn,
        mime=m,
        status="unsupported",
        text="",
        truncated=False,
        error_reason=None,
    )


def _extraction_summary_line(r: DocumentExtractionResult) -> str:
    if r.status == "unsupported":
        return "unsupported for this format"
    if r.status == "failed":
        er = (r.error_reason or "error").replace("\n", " ").strip()[:120]
        return f"failed ({er})"
    if r.status == "empty":
        return "empty (no extractable text in this slice)"
    if r.status == "truncated":
        suffix = f" or first {MAX_PDF_PAGES} PDF pages" if r.mime == "application/pdf" else ""
        return f"truncated after {MAX_EXTRACTED_CHARS_PER_FILE:,} characters{suffix}"
    if r.truncated:
        return f"extracted, truncated after {MAX_EXTRACTED_CHARS_PER_FILE:,} characters"
    return "extracted"


def format_document_block_for_llm(r: DocumentExtractionResult, *, content_body: str) -> str:
    """One document block for the model. ``content_body`` is already bounded."""
    return (
        f"[Attached document: {r.filename}]\n"
        f"Type: {r.mime}\n"
        f"Extraction: {_extraction_summary_line(r)}\n"
        f"Content:\n{content_body}\n"
    )


def format_document_placeholder_for_llm(r: DocumentExtractionResult) -> str:
    """No extractable body: unsupported, empty, or failed — short placeholder."""
    name = r.filename
    mime = r.mime
    if r.status == "unsupported":
        return (
            f"[Attached document: {name}]\n"
            f"Type: {mime}\n"
            "This file was attached, but text extraction for this format is not enabled in this deployment."
        )
    if r.status == "failed":
        return (
            f"[Attached document: {name}]\n"
            f"Type: {mime}\n"
            f"Extraction: {_extraction_summary_line(r)}\n"
            "Content:\n[Text extraction did not succeed; the file is still attached for your reference.]"
        )
    if r.status == "empty":
        return (
            f"[Attached document: {name}]\n"
            f"Type: {mime}\n"
            f"Extraction: {_extraction_summary_line(r)}\n"
            "Content:\n[No extractable text — the document may be scanned or image-only (OCR is not enabled).]"
        )
    return format_document_block_for_llm(r, content_body=r.text)


def _skipped_budget_block(r: DocumentExtractionResult) -> str:
    return (
        f"[Attached document: {r.filename}]\n"
        f"Type: {r.mime}\n"
        "Extraction: omitted — attached-document text budget exhausted for this message\n"
        "Content:\n[This file was not included in the extracted context due to size limits.]"
    )


def build_document_llm_sections(
    results: list[DocumentExtractionResult],
    *,
    max_total_chars: int = MAX_EXTRACTED_CHARS_PER_MESSAGE,
) -> list[str]:
    """
    Per-file sections for the LLM, enforcing ``max_total_chars`` on *extracted* body text.
    Placeholder sections (unsupported/failed/empty) do not consume the character budget.
    """
    sections: list[str] = []
    budget = max_total_chars
    for r in results:
        if r.status in ("unsupported", "failed", "empty"):
            sections.append(format_document_placeholder_for_llm(r))
            continue
        body = (r.text or "").strip()
        if not body:
            sections.append(format_document_placeholder_for_llm(r))
            continue
        if budget <= 0:
            sections.append(_skipped_budget_block(r))
            continue
        if len(body) <= budget:
            sections.append(format_document_block_for_llm(r, content_body=body))
            budget -= len(body)
            continue
        take = body[:budget]
        summary = (
            _extraction_summary_line(r)
            + f" — truncated ({MAX_EXTRACTED_CHARS_PER_MESSAGE:,} character total budget for attached documents)"
        )
        sections.append(
            f"[Attached document: {r.filename}]\n"
            f"Type: {r.mime}\n"
            f"Extraction: {summary}\n"
            f"Content:\n{take}\n"
        )
        budget = 0
    return sections

