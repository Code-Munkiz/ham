# HAM product roadmap (workspace, attachments, export)

Durable planning doc for **dashboard / workspace chat**, **attachments**, **export**, and closely related capabilities. It complements subsystem-specific roadmaps (for example [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md), [`ham-x-agent/`](ham-x-agent/) Phase 2A/2B/2C).

**Naming note:** **Phase 2B–2F** below mean **attachment parity + export + media + RAG** sequencing for the Hermes workspace. Other areas (HAM-on-X, Browser Operator) use different phase labels in their own docs—see grep hits for `Phase 2B` elsewhere.

This file is **documentation only**; it does not imply shipped code unless a line explicitly says shipped.

---

## 1. Current accepted baseline (post–Phase 2A)

Snapshot accepted after Document Intelligence Phase 2A and backend deploy:

| Area | State |
|------|--------|
| Document extraction | `.txt`, `.md`, `.pdf`, `.docx` — bounded extraction, server-side only into LLM request assembly |
| Legacy Word | `.doc` — store-only / unsupported extraction (honest placeholder to model) |
| Image vision | Still supported via existing multimodal path |
| Attachment storage | GCS-backed `AttachmentStore`; `/api/chat/attachments`; no parallel `/api/upload` stack |
| Session payload security | `ham_chat_user_v2` stays refs only (id, name, mime, kind); no extracted bodies in Firestore/session summaries/operator plain text |
| Hermes gateway | HTTP mode to private Hermes; upgrade process documented — target tag **v2026.4.23** per [`HERMES_UPGRADE_RUNBOOK.md`](HERMES_UPGRADE_RUNBOOK.md) |
| Backend | Cloud Run `ham-api` (staging/prod per deploy docs) |
| Git | `main` aligned with team remote after Phase 2A push; baseline feature commits include document extraction and test fix (see history for `feat(chat): extract document attachment text` and follow-ups) |

**Labels (accepted gate):**

- `DOCUMENT_INTELLIGENCE_PHASE_2A_DEPLOYED`
- `PHASE_2A_FULLY_ACCEPTED`
- `IMAGE_VISION_REGRESSION_CHECK_PASSED`
- `NO_PATH_OR_GS_LEAKAGE_CONFIRMED`
- `GCS_ATTACHMENT_STORE_PRESERVED`
- `HERMES_UNCHANGED` (no Phase 2A requirement to redeploy Hermes VM for document extraction)

---

## 2. Non-negotiable architecture rules

- **Browser never calls provider LLM APIs directly** — traffic goes **Browser → HAM API → Hermes / gateway**.
- **Browser never holds or calls Cursor/vendor APIs for secrets** — Cursor Cloud Agent flows go **Browser → HAM API →** allowed server paths (see Cloud Agent docs).
- **Single attachment pipeline** — use **`POST /api/chat/attachments`** and **GCS `AttachmentStore`**; do not introduce a second upload stack (no new `/api/upload` for chat files).
- **No path or secret leakage** in user-visible chat, API responses to the browser, or logs: no local filesystem paths, no `gs://` object paths, no provider tokens, no raw env values in client-facing payloads.
- **Extracted document text** is **ephemeral server-side** for model context only: **not** in persisted `ham_chat_user_v2`, session list summaries, mission metadata, browser attachment metadata, or logs.

---

## 3. Completed phases (high level)

- **Attachment foundation** — composer upload, drag/drop, Ctrl+V images, previews, file cards.
- **GCS durable attachment store** — shared blobs for multi-instance Cloud Run; opaque attachment ids.
- **Hermes vision routing** — multimodal forwarding per gateway mode and env caps.
- **Hermes upgrade** — **v2026.4.23** (and VM disk runway) documented in [`HERMES_UPGRADE_RUNBOOK.md`](HERMES_UPGRADE_RUNBOOK.md).
- **Document Intelligence Phase 2A** — `src/ham/chat_document_extraction.py`, wiring in `chat_user_content.py`, tests, `pypdf` / `python-docx` in `requirements.txt`.

---

## 4. Active roadmap (priority order)

**Export-to-PDF is the next major product slice** after Phase 2A—do not defer it behind voice or video.

| Phase | Focus | Notes |
|-------|--------|--------|
| **Phase 2B** | **Export-to-PDF MVP** | Chat transcript first; audit-friendly PDFs; backend-mediated |
| **Phase 2C** | Model capability map + UX copy | Honest modality labels; safe reject/annotate |
| **Phase 2D** | Voice UX polish | Align with existing voice/dictation; no duplicate stack |
| **Phase 2E** | Video attachment intelligence | Store, thumbnail, transcript, keyframes; bounded context |
| **Phase 2F** | File retrieval / search / RAG | Chunk, retrieve, cite; tenant/session scoped |

---

## 5. Phase 2B — Export-to-PDF MVP (definition only)

**Purpose:** Let users export selected HAM outputs as **clean, audit-friendly PDFs** without exposing secrets or storage internals.

**Candidate surfaces (later phases after MVP):**

- Chat transcript (MVP)
- Document summary (if represented as visible chat turns / summaries only)
- Mission / War Room report
- Cloud Agent plan/result
- Audit evidence bundle
- Attachment intelligence summary

**MVP scope:**

- Start with **chat transcript export** (current session or selected range — to be decided in implementation prompt).
- **Backend-mediated** generation preferred for consistency with redaction and audit.
- **No provider calls from the browser** for PDF generation.
- **No secret/env/path/`gs://` leakage**; sanitize HTML/Markdown; safe filenames and titles only.
- **Timestamps** and **project/session labels** where safe and already known to the API.
- **Clear title / header / footer** (minimal HAM branding is enough for MVP).

**Out of scope for MVP:**

- Full “evidence bundle composer”
- PDF editing (use dedicated tools; **nano-pdf**-style flows are for editing existing PDFs, not primary generation here)
- OCR, video reports, RAG citations
- Signed external share links
- Heavy custom branding

**Implementation direction (investigation — no deps added by this roadmap):**

| Approach | Pros | Cons |
|----------|------|------|
| **Playwright / Chromium PDF** | Already in Cloud Run–style images; pixel-stable printing | Heavier runtime; must sandbox content |
| **WeasyPrint** | Good HTML→PDF | Native deps on Linux images |
| **ReportLab** | Full control; no browser | More code for layout |
| **wkhtmltopdf** | Simple if binary present | Extra image weight; maintenance |

**Recommendation for Phase 2B implementation prompt:** Prefer **Playwright/Chromium PDF** or server-rendered HTML → print if the **`ham-api` image already ships Playwright** (see [`BROWSER_RUNTIME_PLAYWRIGHT.md`](BROWSER_RUNTIME_PLAYWRIGHT.md)); otherwise evaluate **WeasyPrint** vs **ReportLab** for a smaller footprint.

**MVP shipped:** **ReportLab** — `GET /api/chat/sessions/{session_id}/export.pdf` (sanitized transcript; no attachment re-fetch) and workspace **Export PDF** button. Evolve to Playwright/HTML layout in a later iteration if needed.

**Authorization note:** Export uses the **same Clerk gate** as `GET /api/chat/sessions/{id}`. The session store **does not** attach an owner/user id to each session; **session_id secrecy** is the practical access control (same as fetching JSON history). Per-user session isolation is a separate persistence effort.

### Security rules (Phase 2B)

- Sanitize Markdown/HTML; strip script, remote assets, and opaque metadata where applicable.
- Do not include provider tokens, env dumps, local paths, `gs://` URIs, raw storage keys, or hidden chain/tool payloads.
- **Do not pull raw attachment bytes into the PDF** unless explicitly designed and user-visible—default is **transcript + safe attachment filenames**, not re-extraction.

**Acceptance criteria (when Phase 2B is implemented):**

- User can export **current chat transcript** to PDF.
- PDF includes readable title, timestamps, user/assistant turns, **safe attachment filenames** as references.
- PDF **excludes** secrets, paths, `gs://`, provider metadata.
- Works when chat referenced document summaries (text already in transcript/model-visible history—no new attachment reprocessing unless specified).
- Tests cover **sanitizer / path redaction**.
- Manual smoke: browser download works end-to-end.

**Labels:**

- `PDF_EXPORT_ROADMAP_ADDED`
- `PDF_EXPORT_PHASE_2B_DEFINED`
- `PDF_GENERATION_SKILL_GAP_ACKNOWLEDGED` (explicit design choice in implementation PR)
- `PHASE_2A_SCOPE_REMAINS_CLOSED` (this doc does not expand Phase 2A)

---

## 6. Phase 2C — Model capability map + UX copy (brief)

**Purpose:** Know which models support text, image, document context, audio, video, tool use, long context—surface **honest** UI copy and safe server behavior.

**Acceptance:** Central capability registry (source TBD); UI uses capability-aware strings; backend rejects or annotates unsupported modalities without silent corruption.

---

## 7. Phase 2D — Voice UX polish (brief)

**Purpose:** Polish dictation / voice chat; align with existing voice work; one architecture.

**Acceptance:** Reliable recording/transcription states; clear errors; no accidental auto-send unless intended; no token leakage.

---

## 8. Phase 2E — Video attachment intelligence (brief)

**Purpose:** Store video attachments; thumbnail; audio transcript; keyframes; **bounded** context injection.

**Out of scope:** Full video editing; unbounded processing; provider calls from frontend.

---

## 9. Phase 2F — File retrieval / search / RAG (brief)

**Purpose:** Search across uploaded docs; retrieve chunks; preserve tenant/session auth; safe citations.

**Out of scope:** Cross-user retrieval; unscoped global memory; leaking storage paths.

---

## 10. Next build prompts (execution queue)

**Next implementation prompt:**

**HAM Phase 2B — Export-to-PDF MVP for chat transcripts**

That prompt should investigate:

- Existing chat/session **read** APIs and where transcript text is assembled.
- Whether Markdown/HTML rendering exists server- or client-side for sanitization.
- Best PDF approach for **Cloud Run** image (see §5).
- **Download** endpoint design (`Content-Disposition`, auth, rate limits).
- Frontend control placement (Workspace chat chrome).
- **Sanitizer/redaction** tests and negative cases (path/token/`gs://`).

---

## 11. Related docs

- [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md), [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md)
- [`HERMES_UPGRADE_RUNBOOK.md`](HERMES_UPGRADE_RUNBOOK.md)
- [`HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md)
- [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md)

---

**Decision labels (this doc):** `HAM_ROADMAP_CREATED`, `PDF_EXPORT_PHASE_2B_DEFINED`, `PDF_EXPORT_ROADMAP_ADDED`, `PHASE_2A_SCOPE_REMAINS_CLOSED`.
