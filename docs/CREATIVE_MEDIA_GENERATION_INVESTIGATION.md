# Creative media generation — HAM Phase 2G investigation

**Status:** documentation / architecture spike only (**no routes, keys, frontend buttons, or provider integration added in this document**).

**Goal:** Recommend the safest way for HAM to support **high-quality image and video generation** from prompts while preserving:

- **Browser → HAM API → provider / media gateway** (never browser → provider for generation or keys)
- No provider keys or raw secrets in the frontend
- **Generated** media persisted under HAM-controlled storage + **opaque download/ref** semantics
- **Capability-aware**, honest UX copy distinguishing **consumption vs generation**, **HAM export vs model PDF**, **video attachment vs video understanding/generation**

**Related:** User-upload lifecycle remains **`POST /api/chat/attachments`** + GCS **`AttachmentStore`** (Phase 2A–2E). **Generated** assets are a **different product object** — see §6.

Official provider documentation should be verified before implementation (URLs below are indicative; schemas and pricing drift).

---

## 1. Product validation — does generation “ride along” with the chosen chat LLM?

**Expected answer:** **No, not automatically.**

**Rationale:**

- Workspace **chat routing** selects a **text/multimodal chat** SKU for Hermes/OpenRouter/`http` gateways. Its **capabilities** (vision **input**, document extraction context, transcript PDF **export**) are **orthogonal** to **generative media** modalities.
- Providers expose **generation** models and APIs (often different endpoints, quotas, modality flags, async jobs). Conflating `image_input` or `supports_chat` with `supports_image_generation` causes **incorrect capability UI** and **accidental billing**.

**HAM needs a deliberate “media capability layer”** — server-side union of catalog metadata + provider metadata + conservative defaults (`false` unless proven).

---

## 2. HAM codebase audit (Phase 2G baseline)

### Labels

- **`CREATIVE_MEDIA_BASELINE_AUDITED`**
- **`GENERATED_MEDIA_STORE_NOT_PRESENT`** — **as of the original investigation baseline** there was **no** first-class store; **Phase 2G.1** adds `src/ham/generated_media_store.py` with `hamgm_*` ids + local/GCS backends (see **MVP implementation notes** at end of this doc).
- **`MEDIA_PROVIDER_ADAPTER_NOT_PRESENT`** — no `CreativeMediaProvider` abstraction; **`src/llm_client.py`** wraps **LiteLLM + OpenRouter** for **chat completions** only, not Images/Videos endpoints.

### Current capability payload (`GET /api/chat/capabilities`)

Implemented in **`src/ham/model_capabilities.py`** (`build_chat_capabilities_payload`):

| Field | Semantics today |
|--------|------------------|
| `text_chat` | Always true |
| `image_input` | Heuristic from **chat model id** (vision SKU guess) |
| `document_text_context` | HAM text extraction pipeline (bounded) |
| `native_pdf` | False |
| `audio_input` | False |
| `video_input` | False (**not** “video generation”; means native video-to-model ingestion) |
| `pdf_export` | HAM transcript PDF download |
| `tool_use` | False |

**Frontend mirror:** `frontend/src/lib/ham/types.ts` → `ChatCapabilitiesPayload`.

**Gaps:** No `supports_*_generation`, no async-job flags, no reference-image flags for **generation**.

### Gateway / broker

- **`src/ham/hermes_gateway/`** — snapshot/probe adapters for Hermes HTTP, CLI hints, degraded capabilities; **no** media-generation wiring.
- **Chat streaming** flows through **`/api/chat/stream`** and gateway paths in **`src/api/chat.py`** (Hermes-mediated); unrelated to outbound image synthesis today.

### User artifacts vs generated artifacts

- **`AttachmentStore` / `AttachmentRecord`** — **user uploads**, opaque ids, Clerk `owner_key` when auth on; surfaced via **`GET /api/chat/attachments/{id}`**.
- **`GET …/sessions/{id}/export.pdf`** — **server-rendered transcript** artifact (different trust model from user upload).
- **Generated images/videos** should **not** overload “attachment” semantics without clear typing — risk of mixing **quota**, **lifecycle**, **content policy**, and **vision-forwarding** logic.

### Dockerfile / deps

Same baseline as **`VIDEO_PROCESSING_INVESTIGATION.md`**: **`python:3.12-slim-bookworm`** + Playwright/Chromium — **no** bundled creative-media runtime beyond what providers offer via HTTP APIs.

### Where routes would attach later

- **HAM API**: new `/api/media/...` (or namespaced **`/api/creative-media/...`**) routers colocated with existing auth (**Clerk** / operator headers).
- **`model_capabilities`** (or **`/api/models` enrichments**) — propagate **generation** modality flags separately from **`image_input`**.

---

## 3. Provider / API landscape (research summary)

### Labels

- **`CREATIVE_MEDIA_PROVIDER_OPTIONS_RESEARCHED`**
- **`OPENROUTER_MEDIA_CAPABILITIES_VERIFIED`** — at architecture level via public docs (**no keys** in repo); re-verify schemas at ship time.
- **`MEDIA_PROVIDER_RISKS_DOCUMENTED`**

Comparison is qualitative; pricing and SKUs move often.

| Dimension | OpenRouter ([image](https://openrouter.ai/docs/guides/overview/multimodal/image-generation), [video](https://openrouter.ai/docs/guides/overview/multimodal/video-generation)) | OpenAI Images / Responses ([image gen](https://developers.openai.com/docs/guides/image-generation)) | Typical Replicate-like hosts | Specialized video SaaS |
|-----------|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|-------------------------------|---------------------------|
| **Fit HAM mediated** | ✅ Single API key server-side | ✅ Dedicated image APIs + org controls | ⚠ Separate vendor; still OK if **backend-only** keys | ⚠ Contract + egress review |
| **Text → image** | ✅ `modalities` / image output models | ✅ Generations endpoint | ✅ Model cards vary | Depends |
| **Image edit / i2i** | Depends on routed model | ✅ Edits / multi-image flows (per docs) | ✅ Common | Depends |
| **Text → video** | ✅ **`POST /api/v1/videos`** async job ([create](https://openrouter.ai/docs/api/api-reference/video-generation/create-videos)) | Evolving separately from chat | ✅ Many models | ✅ Native |
| **Image → video** | Docs reference optional reference images ([video guides](https://openrouter.ai/docs/guides/overview/multimodal/video-generation)) | Provider-dependent | ✅ | ✅ |
| **Sync vs async** | Images often inline in chat completions; video **poll + download** (`GET …/videos/{id}`, content route) | Image often sync; streaming options for some tiers | Mixed | Mostly async |
| **Auth model** | `Authorization` bearer on server | Same | Bearer / signed requests | JWT / API keys |
| **URLs / downloads** | May return **`data:` / short-lived URLs** upstream — HAM **must normalize** → **HAM-stored blobs** before exposure | Same | Signed URLs frequent | Signed |
| **Webhooks vs poll** | Video flow described as poll-oriented in OpenRouter multimodal docs | Webhooks vary by OpenAI offering | Often webhook callbacks | SaaS-dependent |
| **Safety** | Router + model provider policies | OpenAI moderation / org rules | Repo-specific | Custom |
| **Risks** | Token/credits coupling; modality discovery must track **catalog** | Vendor lock slice; GPT Image gated per org docs | Operational surface + egress | Highest integration cost |

**Reference-only names** (research only — not endorsed without security review): **Runway**, **Luma**, **Kling**, etc., as alternate video backends **via the same mediated adapter**.

**Self-hosted diffusion** remains **future / heavier ops** unless product mandates it.

---

## 4. Proposed HAM **media capability model** (`GET /api/chat/capabilities` extension)

### Labels

- **`MEDIA_CAPABILITY_MODEL_DEFINED`**
- **`MEDIA_CAPABILITY_SEMANTICS_CLARIFIED`**
- **`UNKNOWN_MEDIA_CAPABILITIES_ARE_CONSERVATIVE`**

Extend `capabilities` (or parallel `generation` object — **recommended** nested object to avoid bloating unrelated flags):

```yaml
generation:
  supports_image_generation: bool        # default false
  supports_image_editing: bool           # inpaint / remix / mask flows
  supports_image_to_image: bool          # structural i2i
  supports_video_generation: bool       # provider can create video pixels
  supports_image_to_video: bool
  supports_video_editing: bool          # trims/cuts — usually false MVP
  supports_async_media_jobs: bool       # true when video/async path required
  supports_reference_images: bool       # user attachment ids or inline refs ok
  generated_media_max_duration_sec: number | null
  generated_media_max_resolution: string | null   # opaque W×H tier label; no UX pixel promise if unknown
  generated_media_output_types: string[]           # ["image/png", "video/mp4"] sanitized
  media_generation_provider_slug: string | null    # e.g. openrouter vs openai — non-secret discriminator
  media_generation_notes: string[]                 # short honest strings (cost, latency)
```

### Semantics (must not collide)

| Term | Means |
|------|--------|
| `image_input` | User/image **consumption** (vision forwarding) |
| `supports_image_generation` | Pixel **creation** pipeline available |
| `video_input` | **Native** multimodal video to LLM (**not currently HAM MVP**) |
| Video **attachment store-only** | User file **storage** (`kind: video`) — **≠** generation |
| `pdf_export` | **HAM** transcript PDF — **≠** “model authored PDF artifact” |

**Unknown SKU → all generation booleans false** + explicit **`limitations`** line (“Image/video generation unavailable for selected configuration.”).

---

## 5. Architecture options

### Labels

- **`GENERATED_MEDIA_ARCHITECTURE_OPTIONS_COMPARED`**
- **`CREATIVE_MEDIA_ARCHITECTURE_RECOMMENDED`**

| Option | Summary | Pros | Cons |
|--------|---------|------|------|
| **A — Direct REST endpoints** | `POST /api/media/images/generate`, `POST …/videos`, `GET …/jobs/{id}` | Clear quotas, CDN-friendly retries, aligns with OAuth/Clerk | More surface to secure |
| **B — Chat-only tool path** | Model tool → backend adapters | Leverages conversational affordance | **Hard to gate UX/cost**, ambiguous “who chose model”, brittle if chat model unrelated |
| **C — Hybrid (recommended)** | Dedicated UI + endpoints + transcript references | Predictable UX, explicit consent, aligns with investigator default | Requires UI work after API |
| **D — Provider tool-use only** | Let remote tool runtime own media | Less HAM glue | Violates centralized policy/audit/logging; inconsistent storage |

### Recommended default

**Option C**, implemented by **establishing backend media adapters first**:

1. **Backend service module** translating HAM intents → chosen provider payloads (never raw provider dump to browsers).
2. **Dedicated synchronous image route** MVP; **async job + polling** MVP for video.
3. Hermes/router **may call** adapters later behind **HAM-owned tools** once stable — **Hermes codebase unchanged per current charter**.
4. **Storage:** new **generated-media persistence** beside `AttachmentRecord` (**see §6**).

---

## 6. Generated artifact storage model

### Labels

- **`GENERATED_MEDIA_STORAGE_MODEL_PROPOSED`**
- **`NO_RAW_STORAGE_PATHS_IN_MEDIA_API`**

Do **not** reuse user-upload `attachment_id` prefixes without a distinguishing **namespace**.

**Suggested record** (persistent metadata; binary in GCS or same bucket segregated):

| Concept | Visibility |
|---------|-------------|
| `generated_media_id` | Opaque **`hamgm_`** style token exposed to frontend |
| `job_id` | Provider job id (**internal**) + mirrored public only if sanitized |
| `session_id`, `project_id` | Associations for listings |
| `prompt_digest` | Truncated / hashed audit field (full prompt policy TBD privacy) |
| `provider_slug`, `model_id` | Non-secret discriminator |
| `media_type` | `image` \| `video` |
| `status` | `queued` \| `processing` \| `ready` \| `failed` \| `canceled` |
| `mime_type`, `size_bytes`, duration, WxH | When known |
| `safe_display_name` | User-visible filename suggestion |
| `storage_ref_internal` | **Never** echoed to client verbatim |
| `public_url` | **No default** |

**Serving:** `GET /api/media/generated/{generated_media_id}/download` (**Stream**), same auth posture as attachments.

Rules:

- **No `gs://`**, filesystem paths, or raw signed upstream URLs returned in JSON/HTML.
- **Sanitize prompts** logged; omit provider request IDs unless redacted.
- **Retention cap** enforced (TTL purge job later).

---

## 7. Staged roadmap (recommended)

### Labels

- **`CREATIVE_MEDIA_PHASE_SEQUENCE_DEFINED`**
- **`IMAGE_GENERATION_MVP_DEFINED`**
- **`VIDEO_GENERATION_MVP_DEFERRED_UNTIL_ASYNC_READY`** (polling + quotas first)

| Phase | Scope |
|-------|-------|
| **2G.1** | **Image generation MVP** — text-to-image **only**; **sync** backend path; persisted PNG/WebP/WebM as configured; **`GET …/capabilities`** reflects flags; transcript card shows reference (not raw external URL).
| **2G.2** | **Editing / image-to-image** — reference **`attachment_id`** for source image; mediated edit endpoints.
| **2G.3** | **Video generation** — **async**: create job (`POST`), poll (`GET`), download via HAM (**strict duration/resolution ceilings**).
| **2G.4** | **Generated media gallery** — list per session/project, reuse refs in chat payloads, revoke/delete.

Hermes/agent/SSE untouched until **HAM-owned** HTTP paths are hardened.

---

## 8. Security & cost envelope

### Labels

- **`CREATIVE_MEDIA_SECURITY_MODEL_PROPOSED`**
- **`CREATIVE_MEDIA_COST_CONTROLS_PROPOSED`**

Starter **limits** (tune during 2G.1 QA):

| Control | Starter guess |
|---------|----------------|
| Images per burst | 1–4 synchronous |
| Max output resolution | Tie to SKU max or downscale server-side |
| Prompt length cap | Typical 4k–8k Unicode safe strip |
| Reference image aggregate size | Respect existing **`HAM_CHAT_ATTACHMENT_MAX_BYTES`** or stricter tier |
| Video duration/resolution/product | Lowest paid tier acceptable; concurrency **1–2**/user/session |
| Job wall timeout | Bounded **poll stop** → user-visible cancel |
| Retention | 7–30d default / admin policy |
| Max download/stream | Mirrors stored object cap |

Cost rules:

- **Video** flows require **explicit UX affordance + confirmation**.
- Disable **silent auto-retries** on provider 429/5xx unless idempotent bookkeeping exists.

---

## 9. Implementation sketch — Phase **2G.1** only (later PR)

Likely additions:

| Area | Responsibility |
|------|------------------|
| `src/ham/creative_media/*.py` | Provider adapters (`OpenRouterImageClient`, `OpenAIMediaClient` façade) returning **normalized bytes + metadata**. |
| `src/ham/generated_media_store.py` | GCS + Firestore/meta mirror (dual-write atomicity pattern). |
| `src/api/media_generation.py` (router) | **Clerk**/operator guarded routes. |
| `src/ham/model_capabilities.py` (+ tests) | New nested **generation** block or flat flags wired from env + SKU table. |
| `frontend/src/...` (later, gated) | Capability-driven affordances (**not** part of this investigation commit). |

---

## MVP implementation notes (Phase 2G.1 — shipped, backend-only)

These notes supplement §5–§7; **no rewrite** of the architecture sections above.

### HTTP surface

- **`POST /api/media/images/generate`** — JSON `{ "prompt": str, "model_id"?: str }`; returns `{ generated_media_id, media_type, mime_type, status, download_url }` plus optional `width`/`height` when known. Relative **`download_url` only** (same origin); **no** raw provider URLs, **`gs://`**, or storage keys in JSON.
- **`GET /api/media/artifacts/{id}`** — safe metadata + same relative `download_url`.
- **`GET /api/media/artifacts/{id}/download`** — bytes, `Cache-Control: no-store`, `Content-Disposition: attachment`.

### Auth / isolation

Same **Clerk session optional** posture as chat attachments: when a Clerk user is present, generated rows record **`owner_key`** and download/metadata require the same user; when absent (local dev), artifacts are **world-readable** by id (rely on id secrecy — same class as attachment downloads without owner).

### Persistence

- **Ids:** `hamgm_` prefix (`src/ham/generated_media_store.py`).
- **Local (default):** `HAM_GENERATED_MEDIA_DIR` or `HAM_DATA_DIR/generated-media`.
- **GCS:** `HAM_GENERATED_MEDIA_STORE=gcs` and **`HAM_GENERATED_MEDIA_BUCKET`** or fallback to **`HAM_CHAT_ATTACHMENT_BUCKET`** with prefix **`HAM_GENERATED_MEDIA_PREFIX`** (default `generated-media/`). **Do not** point production at ephemeral local disk without accepting data loss.

### Provider / env (text-to-image)

- **Feature flag:** `HAM_MEDIA_IMAGE_GENERATION_ENABLED` (`1` / `true` / `yes` / `on`).
- **Key:** existing **`OPENROUTER_API_KEY`** (must pass HAM plausibility checks — same family as chat).
- **Default model:** `HAM_MEDIA_IMAGE_DEFAULT_MODEL` (OpenRouter model id); otherwise pass **`model_id`** on each request.
- **Limits:** `HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS`, `HAM_MEDIA_IMAGE_OUTPUT_MAX_BYTES` (optional).

### Capabilities

`GET /api/chat/capabilities` includes a nested **`generation`** object (`supports_image_generation`, etc.). **Enabled** only when the feature flag **and** a plausible OpenRouter key are present; **not** tied to the selected **chat** model id.

### Explicitly not in 2G.1

Frontend generation control, video generation, image edit / i2i, public CDN URLs, billing UI.

### Phase 2G.2 frontend (implemented)

Hermes workspace chat uses **explicit + menu → Generate image** and deterministic **natural-language routing** only for clear creation phrases (analyze/describe/“what’s in this image” paths stay on normal chat). **No confirmation modal** for obvious generation intent. Generation remains **HAM API-mediated** (`hamApiFetch`): **no browser→provider** calls or keys in the UI; previews use **`ObjectURL`** from **`/api/media/artifacts/{id}/download`**. Capability flag **`generation.supports_image_generation`** gates the action; when unavailable the row stays visible with disabled copy (**no fake generation**).

### Phase 2G.3 reference generation (implemented)

Workspace chat can supply **`reference_attachment_id`** (`hamatt_*`) on **`POST /api/media/images/generate`** so the backend resolves blob bytes from **`AttachmentStore`**, validates image MIME/size, and (when **`HAM_MEDIA_IMAGE_TO_IMAGE_ENABLED`** is not **`false`** and the default generation model heuristic allows it) forwards a multimodal **`user`** message to OpenRouter. **True inpainting/editing SKU guarantees** remain environment-specific — treat **`supports_image_to_image`** as capability-gated scaffolding; **`IMAGE_TO_IMAGE_NOT_SUPPORTED`** (HTTP 503) is returned when the feature is toggled off. Distinct **`supports_image_editing`** remains **False** until a dedicated inpaint/edit path exists. Frontend NL routing prefers **ambiguous-with-attachment → normal vision chat** except for explicit edit/variation wording; **`+ → Generate image`** uses the reference attachment when **`supports_reference_images`** is true.

### Phase 2G.5 provider registry + ComfyUI plan doc (implemented)

- **`src/ham/media_provider_registry.py`** — canonical **`HAM_MEDIA_PROVIDER`** selection; **OpenRouter** when unset-compatible; **`unconfigured`** / missing prerequisites → **`UnconfiguredImageProviderAdapter`**; **`test_synthetic`** only when **`HAM_MEDIA_ALLOW_SYNTHETIC_ADAPTER`** is set; **`comfyui`** participates as a real backend when **`HAM_COMFYUI_BASE_URL`** and generation flag align (**2G.6**); other vendor ids remain **placeholder-unconfigured** adapters.
- **`GET /api/chat/capabilities`** **`generation`** adds **`active_media_provider`**, **`available_media_providers`**, conservative mode flags, **`provider_notes`** — no internal URLs / keys.
- **`docs/COMFYUI_PROVIDER_PLAN.md`** — architecture, env table, Phase **2G.7** operator checklist.

### Phase 2G.10 video UI MVP (implemented)

- Workspace chat adds explicit **`+ → Generate video`** (capability-gated) and does not auto-intercept normal text prompts for video in this slice.
- Frontend calls backend async endpoints (`POST /api/media/videos/generate`, poll `GET /api/media/jobs/{id}`), then resolves the final artifact through the same safe generated-media metadata/download routes.
- Generated video cards render queued/running/failed/succeeded states with `<video controls>` and a backend-mediated download action only.

### Phase 2G.6 ComfyUI adapter + SDXL templates (implemented)

- **`src/ham/comfyui_provider_adapter.py`** — loads **`configs/media/comfyui/`** manifests, **`POST /prompt`**, polls **`GET /history/{prompt_id}`**, retrieves bytes from **`GET /view`** server-side only; rejects reference inputs early (**`IMAGE_TO_IMAGE_NOT_SUPPORTED`**).
- **`sdxl_baseline.manifest.json`** + **`sdxl_baseline.workflow.example.json`** encode **sdxl** graph patch points (**license_check_required**) without committing checkpoint binaries.
- Tests use **mocked httpx**; live GPU worker integration is explicitly **Phase 2G.7** operator territory.

### Phase 2G.7 Comfy worker targets + profile hints (implemented in docs / ergonomics)

- **`docs/COMFYUI_WORKER_TARGETS.md`** + **`configs/media/comfyui/worker_targets.example.json`** — default **`local_gpu_workstation`** POC framing; warns **Cloud Run cannot hit laptop `localhost`** without VPN/tunnels; documents future **`dedicated_gpu_vm`**, **`runpod_vast_beam_worker`**, **`managed_comfy_cloud_worker`** setups **without committing URLs**.
- **`HAM_COMFYUI_WORKER_PROFILE`** — allowlisted opaque label echoed as **`generation.comfy_worker_profile`** when Comfy is active (unknown strings suppressed).
- **`sdxl_vanilla`** resolves to **`sdxl_baseline`** manifests (no duplicated graph JSON).
- **SeargeSDXL**: deferred off-repo until custom-node stack proven — **`SEARGE_SDXL_WORKFLOW_DEFERRED`** baseline label.

### Pitfalls to avoid

- Returning provider-generated **temporary URLs directly** without HAM ingestion.
- Folding generated binaries into **`ham_chat_user_v2`** JSON (bloated Firestore payloads).
- **Browser-keyed provider calls**.
- Assuming **chosen chat LLM ≡ generation model**.

---

## References

- OpenRouter multimodal docs (image `/chat/completions` modalities, `/api/v1/videos` async).
- OpenAI image generation/editing docs.
- Existing HAM security rules: **`docs/HAM_ROADMAP.md`** §2 and [**`VIDEO_PROCESSING_INVESTIGATION.md`**](VIDEO_PROCESSING_INVESTIGATION.md) infra cautions (`ffmpeg`/CPU) — analogous **GPU not required** path for SaaS-mediated generation.
