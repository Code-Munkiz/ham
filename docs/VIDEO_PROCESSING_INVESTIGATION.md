# Video processing investigation (HAM Phase 2E.1)

**Status:** documentation / design spike only — no runtime changes in Phase 2E.1.

**Context:** Phase 2E shipped **store-only** video (`.mp4`, `.mov`, `.webm`) via `POST /api/chat/attachments`, GCS-backed `AttachmentStore`, honest UI copy, and a short **path-free** LLM placeholder in `chat_user_content.py`. There is **no** thumbnail, transcript, keyframe extraction, **no** ffmpeg, and **no** video bytes sent to the model.

This document summarizes an audit of the current runtime, compares architecture options, and recommends a **minimal, safe Phase 2E.2 slice** aligned with explicit user control and bounded cost.

---

## 1. Runtime and tooling audit

### Labels

- `VIDEO_PROCESSING_RUNTIME_AUDITED`
- **`FFMPEG_NOT_PRESENT_CONFIRMED`** — ffmpeg is **not** installed in the Ham API Dockerfile; `requirements.txt` has **no** `ffmpeg-python`, MoviePy, OpenCV, etc.

### Docker / base image (`Dockerfile`)

- **Base:** `python:3.12-slim-bookworm`.
- **Extra packages:** Node 22 (Cursor SDK bridge), Playwright **Chromium** (`playwright install --with-deps chromium`).
- **Implication:** Slim image favors small attack surface but **requires an explicit ops decision** to add `ffmpeg` (or another decoder) via `apt-get`/`RUN` plus image size/regulatory review — **do not merge without approval**.

### `requirements.txt`

- Heavy media/Python bindings **absent**. Document stack uses `pypdf`, `python-docx`, `openpyxl`; no video stack.

### GCS attachments (`src/ham/chat_attachment_store.py`)

- `get(aid)` returns **full `(bytes, AttachmentRecord)`** into process memory — fine for capped sizes, **risky if video caps rise** without streaming or chunked processing.
- **No `gs://` in API responses today** for attachment payloads; blobs are keyed by opaque `hamatt_*` ids.

### LLM assembly path (`src/ham/chat_user_content.py`)

- On chat send / model prep, **`store.get`** loads attachment bytes **synchronously** for files/videos/images in-scope.
- Video branch today only appends `_format_video_llm_placeholder` (no decoding).

### Document extraction (`src/ham/chat_document_extraction.py`)

- Video MIME returns `unsupported`-style semantics if ever fed; **prefer a dedicated `video_processing` module** for Phase 2E.2 rather than growing document extraction further.

### Transcription (`src/api/chat.py`)

- **`POST /api/chat/transcribe`** — multipart upload, Clerk gate, **`_MAX_TRANSCRIBE_BYTES = 15 MiB`**, **`httpx` timeout 120s** upstream to OpenAI `v1/audio/transcriptions`.
- **Reuse for video:**
  - The endpoint expects **audio** content types (`audio/webm`, etc.), not muxed video.
  - **Safe reuse pattern:** bounded **ffmpeg (or equiv.) extract audio → short WAV/MP3/opus blob** → call **same backend transcription path** (shared helper, not necessarily the identical HTTP route) with **strict duration/size caps**.
  - **Risk:** stuffing full muxed `.mp4` into OpenAI as “audio” without extraction is brittle and violates clear MIME semantics — **avoid**.

### Other temp-file patterns (`src/api/audio_upload.py`)

- **`tempfile`** and **`AUDIO_UPLOAD_DIR`** default `/tmp/audio_uploads` for a **legacy/non–chat-attachments** upload path — shows Ham already uses ephemeral disk patterns; Cloud Run **`/tmp` is writable** but **bounded** (~emptyDir size varies by revision config).
- Phase 2E.2 temporary decode output must use **explicit size caps + `finally` cleanup** (unlink under unique prefix).

### Cloud Run suitability (timeouts / concurrency)

- **Request timeout:** default Cloud Run invoke timeout is configurable (often 300s for HTTP); long synchronous video jobs **risk 504 / client abort** unless duration is capped tightly.
- **Memory:** Deploy scripts/docs commonly use **2Gi** for Playwright/Chromium — still **OOM risk** if loading **full decoded frames** without bounds.
- **Concurrency:** Heavy CPU ffmpeg on sync path **limits instance throughput** unless CPU scaled or workload offloaded.

### Sync vs async (high level)

| Approach | Fits today’s codebase | Fits user “non-blocking” goal |
|---------|-------------------------|-------------------------------|
| **Sync bounded** on dedicated “Process” action | ✅ Small change surface; caller waits only for explicit action | ✅ Chat send stays fast if processing is **never** implicit on send |
| **Implicit sync on chat send** | ✅ Technically simple | ❌ Violates latency + timeout risk |
| **Async queue** | ⚠ Requires job store + worker contract + UI status | ✅ Best long-term for long media |

---

## 2. Architecture options compared

### Label

- `VIDEO_PROCESSING_OPTIONS_COMPARED`
- `SYNC_VIDEO_PROCESSING_RISK_ASSESSED`
- `ASYNC_VIDEO_PROCESSING_RISK_ASSESSED`

### Option A — Synchronous bounded processing **on chat send**

- **Pros:** Easiest mentally; reuse same request as message.
- **Cons:** **`ham-api` timeouts**, user-perceived hangs, spikes memory/CPU, hard to retry without duplicating sends. **Fails** Phase 2E non-goals (“block chat indefinitely”). **Rejected** as primary design.

### Option B — Async after upload / background job

- **Pros:** Decouples upload from chat; retries; better cost control knobs.
- **Cons:** Requires **durable job + status**, idempotency, UI poll/SSE/event, lifecycle for partial failures. Cloud Run-only **needs** careful design (**Cloud Tasks / PubSub / second service / VPC** considerations). **Defer** unless product requires long clips or transcription > request budget.

### Option C — Store-only default + explicit **“Process video”**

- **Pros:** Matches **explicit operator consent** (cost predictable), easy to communicate in UX, aligns with Phase 2E shipped behavior (**default store-only placeholder** keeps working). Chat send path stays untouched.
- **Cons:** Extra click; requires clear **busy / failed / ready** UI.
- **Assessment:** **Preferred MVP path** absent strong product requirement for autopilot.

### Option D — External managed media service

- **Pros:** Ops offload decoding/transcode at scale.
- **Cons:** **Data residency / privacy**, contract review, **must remain browser→HAM→vendor** (no client keys); likely **duplicate** AttachmentStore abstraction if not disciplined. Keep as **later** alternate if ffmpeg-in-image rejected.

---

## 3. Recommended MVP (Phase 2E.2 outline)

### Label

- `VIDEO_PROCESSING_PHASE_2E2_DEFINED` (planned; not shipped in 2E.1)

**Recommendation:** Implement **Option C** first: **explicit backend-mediated “Process video”** action on **already-uploaded** `ham_chat_user_v2` refs (opaque `attachment_id`), **bounded** thumbnail + mono/stereo transcript + sparse keyframes, **only after** infra approves ffmpeg (or sanctioned alternative).

**Behavior (target):**

1. Upload stays **`POST /api/chat/attachments`** only.
2. Default LLM placeholder remains unless user triggers process (or stale state).
3. New route e.g. `POST /api/chat/attachments/{id}/video-process` (**name TBD**) or action body with **`attachment_id`** + **Clerk-bound owner check**.
4. Server: download bytes (same store), run **capped ffmpeg** pipelines in `/tmp`, produce:
   - one **JPEG thumbnail** (max dimensions + quality cap),
   - **audio excerpt** capped (e.g. first N seconds) → existing-style **HAM-mediated** transcription helper,
   - **keyframes** count cap (decode + resize + optional brief captions **later** — keep 2E.2 minimal),
5. Persist **derivative artifacts + status** beside attachment (see §4): **prefer same GCS bucket/prefix** with **opaque sibling keys**, never exposing `gs://` to browser.
6. `to_llm_message_content` merges **derived text + optional image refs** **only when `status == ready`**; failures append **honest truncated error** marker, never block unrelated attachments.

Automatic heavy processing **on send** stays **off** unless policy changed with explicit RFC.

---

## 4. Likely implementation touchpoints (Phase 2E.2 — future)

| Area | Files / components |
|------|---------------------|
| Image / deps | `Dockerfile`, `requirements.txt` (only if minimal Python shim needed alongside ffmpeg apt) |
| Core logic | New `src/ham/video_processing.py` (pure functions + caps; subprocess ffmpeg with allowlist args) |
| Storage | Extend `AttachmentRecord` meta **or** sidecar `{id}.video.meta.json` / sibling blobs `"{id}.thumb.jpg"` under bucket prefix (**no user paths**) |
| API | `src/api/chat.py` — new guarded route(s); reuse Clerk + `is_safe_attachment_id` |
| LLM glue | `src/ham/chat_user_content.py` — branch **after** readiness; bounded char budget akin to docs |
| Capabilities copy | `src/ham/model_capabilities.py` — document **honest limits** once feature exists |
| UI | `frontend/.../chat/*` — Process affordance + status badge; keep store-only fallback |
| Tests | `tests/test_video_processing.py`, extend `tests/test_chat_user_content.py` |

### Storage suggestion

Avoid a second arbitrary product store: **reuse `HAM_CHAT_ATTACHMENT_*` bucket** with **namespaced prefixes** (`video-processed/{opaque_id}/...`) written only by **`ham-api`**. **Metadata** ideally on same record as `.meta.json` extension fields or paired JSON blob; **Firestore session** stays **reference-only** (`attachment_id`), not transcript bodies — **matching document extraction precedent**.

---

## 5. Security and limits proposal

### Labels

- `VIDEO_PROCESSING_LIMITS_PROPOSED`
- `VIDEO_PROCESSING_SECURITY_MODEL_PROPOSED`

| Knob | Proposed starter (adjust in PR after profiling) |
|------|-----------------------------------------------------|
| Max source video bytes | Align with **`HAM_CHAT_ATTACHMENT_MAX_BYTES`** (default 20 MiB today) unless product raises cap **explicitly**. |
| Max wall-clock processing per request | Hard cap **`FFMPEG_*` timeouts** subprocess (e.g. 30–60s) shorter than Cloud Run invoke timeout minus headroom. |
| Max `/tmp` usage | **Sum** capped (source copy + WAV + thumbs) · delete in `finally`. |
| Transcript chars | Reuse **`MAX_EXTRACTED_CHARS_*`-style** budget or dedicated **4k–12k** cap for video-audio excerpt only. |
| Keyframes | **3–8** resized JPEG frames max; JPEG width cap e.g. 320–640px. |
| Thumbnail | **1** JPEG, dimension + KB cap. |
| MIME | **`video/mp4`**, **`video/quicktime`**, **`video/webm`** only (same allowlist); reject container tricks via ffprobe whitelist. |

**Security:**

- Never return **local `/tmp`** or **`gs://`** object paths to client.
- **`subprocess`:** fixed argv templates only (no shell); resource limits/timeouts mandatory.
- **Cross-session:** `owner_key` match on **`AttachmentRecord`** mandatory (same pattern as downloads).
- **Sanitize:** transcript passes through existing redaction/stack used for risky doc text if applicable.
- **No executable** decode of macros/script — ffmpeg demux/dec **only**.

**Failure:**

- Failures yield **explicit UI + honest model line** (“processing failed”), **never** wedge Firestore/session JSON size.

---

## 6. Deferred / out of scope (Phase 2E.2+)

- Full RAG over video timelines.
- Native multimodal video model ingest (Hermes/router changes — **Hermes unchanged** per current charter).
- Serverless **async cron** fleets without infra sign-off.
- High-res movie-length transcode pipelines.

---

## 7. Summary decision

| Item | Finding |
|------|---------|
| **ffmpeg** | **Not present**; add only with ops approval (`FFMPEG_NOT_PRESENT_CONFIRMED`). |
| **`/api/chat/transcribe`** | Safe to **reuse pattern** behind **explicit audio extraction** from video — not by posting raw muxed MP4 as “audio”. |
| **Recommended path** | **Option C** — explicit **Process video** optional action + bounded derivatives + readiness-gated LLM context. |
| **Rejected default** | **Option A** implicit on send (**timeout + UX failure**). |
| **Async (Option B)** | **Defer** unless duration/cost forces it. |

For roadmap cross-links, see **Phase 2E.1** in [`HAM_ROADMAP.md`](HAM_ROADMAP.md).
