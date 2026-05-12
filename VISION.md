# Ham — Vision & Architecture

## What Ham Is

Ham is an open-source, multi-agent autonomous developer swarm that executes
the full Software Development Life Cycle (SDLC). It is not a chatbot wrapper.
It is an opinionated assembly line: plan, build, review, learn, repeat.

**Orchestration contract:** supervisory orchestration is **Hermes-led only**.
There is **no CrewAI** (or any other third-party orchestration framework) in
the architecture. `src/swarm_agency.py` assembles per-role context for
Hermes-supervised reasoning surfaces; it does not constitute a parallel
orchestrator.

## Builder platform product north star (aspirational)

Long-term **Builder Platform** vision (last-mile app building, enterprise orchestration, phased roadmap) lives in **[`docs/BUILDER_PLATFORM_NORTH_STAR.md`](docs/BUILDER_PLATFORM_NORTH_STAR.md)**. That document is **not** shipped pillar architecture; Hermes/Droid/context roles and the implementation table below remain authoritative here.

## The Four Core Pillars

### 1. Supervisory Core — Hermes

Hermes is the supervisory control plane for the swarm. It coordinates droids,
routes jobs, critiques outputs, and accumulates learning signals over time.
Hermes owns orchestration and quality policy at the system level.

Hermes may self-handle only tiny, bounded, critic-native tasks (for example:
small review normalization or bounded policy checks). Hermes is not the
primary execution engine.

### 2. Execution Engine — Factory Droid CLI

Factory Droid CLI is the execution-heavy implementation engine. Droid performs
code and shell work (scaffolding, edits, tests, refactors, command execution)
and may self-orchestrate locally while executing delegated work.

Droid is not a dumb worker: it can perform bounded local planning and
sequencing inside an assigned execution job. Ambiguous execution work defaults
to Droid.

### 3. Context Engine — memory_heist.py

Repository-grounded context assembly for the swarm: this module gives every
agent a factual view of the local workspace:

- **Workspace scanning**: filesystem tree, file inventory, ignore rules.
- **Instruction file discovery**: hierarchical SWARM.md / AGENTS.md loading
  from project root up through ancestors.
- **Config discovery**: `.ham.json` / `.ham/settings.json` merge chain.
- **Git state capture**: status, diff, recent log — injected into prompts so
  agents know what changed and what's staged.
- **Session compaction**: conversation history summarization and persistence
  so agents can survive context window limits across long tasks (including
  tool-output pruning and config-driven compaction thresholds).
- **Instruction hygiene**: scanning of discovered instruction files for
  obvious injection patterns and invisible unicode before injection into
  rendered context.

The Context Engine does NOT make decisions. It assembles ground truth and
injects it into agent prompts so they don't hallucinate about repo state.

### 4. LLM Routing — LiteLLM / OpenRouter

LiteLLM and OpenRouter provide model/provider abstraction and routing. Model
selection stays config-driven and decoupled from orchestration and execution
roles.

## Responsibilities Matrix

| Component | Owns | Must Not Own |
|-----------|------|--------------|
| **Hermes (Supervisory Core)** | Job routing, supervisory orchestration, critique policy, learning policy, escalation/handoff decisions | Broad execution loops, heavy code/test/build operations, replacing Droid as execution engine |
| **Droid (Execution Engine)** | Implementation-heavy execution, shell/code operations, bounded local self-orchestration while executing delegated jobs | Global supervisory policy, long-horizon learning governance, replacing Hermes as control plane |
| **memory_heist (Context Engine)** | Repo truth, context discovery/plumbing, instruction/config/git/session context assembly | Execution orchestration policy, critique decision-making, execution ownership |
| **LiteLLM/OpenRouter (Model Routing)** | Provider abstraction, model access, configurable routing | Orchestration policy, execution ownership, critique ownership |

**Default routing rule:** if work may mutate code, invoke tools, or requires
non-trivial execution judgment, route it to Droid.

## Anti-Drift Guardrails (Separation of Duties)

1. **Hermes is not a monolith.** Hermes coordinates, critiques, and learns; it
   does not absorb all runtime behavior.
2. **Hermes is not a second execution engine.** Hermes may run only tiny,
   bounded, critic-native tasks directly.
3. **Orchestration refactors must not absorb execution.** Shifting control flow
   or framework choice must not move execution-heavy behavior into Hermes by
   default.
4. **Droid is not reduced to a dumb worker.** Droid retains bounded local
   self-orchestration authority during execution.
5. **Ambiguous execution defaults to Droid.** If ownership is unclear and task
   impact is execution-heavy, route to Droid first.
6. **No verdict-based role collapse.** Critique outcomes must not be used to
   justify shifting execution ownership away from Droid.

## How They Connect

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────┐
│  Hermes Supervisory Core                    │
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │ route jobs / supervise / critique     │  │
│  └───────────────────────┬───────────────┘  │
│                          │                  │
│                          ▼                  │
│                 ┌──────────────────┐        │
│                 │ Droid CLI        │        │
│                 │ execute + local  │        │
│                 │ self-orchestration│       │
│                 └──────────────────┘        │
│                          │                  │
│                          ▼                  │
│                 ┌──────────────────┐        │
│                 │ Critique + learn │        │
│                 │ (Hermes)         │        │
│                 └──────────────────┘        │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │ memory_heist.py — Context Engine     │   │
│  │ (repo scan, git state, instructions, │   │
│  │  config, session memory)             │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │ LiteLLM / OpenRouter — LLM Routing   │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Architecture Target (North Star)

| Pillar | Target Owner | Target Role |
|--------|--------------|-------------|
| Supervisory Core | `src/hermes_feedback.py` (and Hermes supervisory wiring) | Supervisory orchestration + critique + learning |
| Execution Engine | `src/tools/droid_executor.py` | Execution-heavy implementation with bounded local self-orchestration |
| Context Engine | `src/memory_heist.py` | Repo truth and context plumbing |
| LLM Routing | `src/llm_client.py` | Model/provider abstraction and routing |

## Current Implementation State (Transitional)

| Area | Primary Module(s) | Current Status |
|------|--------------------|----------------|
| Supervisory orchestration | `src/hermes_feedback.py`, `main.py`, `src/swarm_agency.py` (context only) | **Hermes-led:** primary path uses profile selection, Bridge execution, and Hermes (`HermesReviewer`) review; `swarm_agency.py` provides shared `ProjectContext` render budgets for Architect / routing / critic prompts—**not** a separate orchestration engine |
| Execution engine | `src/tools/droid_executor.py` | Bridge v0 bounded backend implemented (`shell=False`, timeout, deterministic capture, capped output) |
| Bridge runtime/policy | `src/bridge/contracts.py`, `src/bridge/policy.py`, `src/bridge/runtime.py`, `src/registry/profiles.py`, `src/registry/backends.py`, `src/registry/droids.py` | Bridge v0 hardened: fail-closed policy gate with command-profile checks, env override restrictions, total-output cap enforcement, deterministic status mapping, mutation-aware refresh gating, and registry-backed profile selection seam with backend-registry executor resolution, plus structured run persistence to `.ham/runs/`; droid registry records for UI/API |
| Read API + run store | `src/api/server.py`, `src/persistence/run_store.py` | Thin FastAPI layer over `RunStore` (`.ham/runs/`): status, runs list/detail, profiles, droids; read-only Context Engine snapshot (`/api/context-engine`, `/api/projects/{id}/context-engine`) for dashboard wiring; **Hermes runtime skills** catalog + host probe + **Phase 2a** shared-target install preview/apply (`/api/hermes-skills/*`, `src/ham/hermes_skills_install.py`, local/co-located only); **v1 allowlisted settings** preview/apply/rollback (`src/ham/settings_write.py`, `src/api/project_settings.py`) writes only `{root}/.ham/settings.json` with backup + audit under `.ham/_backups/settings` and `.ham/_audit/settings` (`HAM_SETTINGS_WRITE_TOKEN` for mutating routes) |
| Workspace Connected Tools (Claude Agent SDK) | `src/api/workspace_tools.py`, `src/ham/worker_adapters/claude_agent_adapter.py` | **`GET /api/workspace/tools`** exposes a **claude_agent_sdk** entry (SDK import + Anthropic / Bedrock / Vertex auth **presence** only — see adapter). Optional **`POST /api/workspace/tools/claude_agent_sdk/smoke`**: feature-flagged (`HAM_CLAUDE_AGENT_SMOKE_ENABLED`), Clerk session or `HAM_CLAUDE_AGENT_SMOKE_TOKEN`, bounded `query()` smoke — **not** Hermes-led orchestration or dashboard chat; dependency pinned in `requirements.txt` for image readiness |
| Capability library (My library) | `src/ham/capability_library/`, `src/api/capability_library.py` | **Phase 1:** per-project **saved** Hermes + capability-directory **refs** in `.ham/capability-library/v1/index.json` (separate from settings); `GET` library + aggregate; **mutations** save/remove/reorder with `HAM_CAPABILITY_LIBRARY_WRITE_TOKEN` and audit under `.ham/_audit/capability-library/`; **no** auto-install, **no** shell; dashboard **Capabilities** page **My library** tab + **Skills** “Save to My Library” (requires `?project_id=`) — installed/active truth remains Hermes/inventory, not the library file |
| Hermes gateway broker (dashboard) | `src/ham/hermes_gateway/`, `src/api/hermes_gateway.py`, `docs/HERMES_GATEWAY_BROKER.md` | **Path B:** `GET /api/hermes-gateway/snapshot` (+ capabilities, optional SSE stream) aggregates hub, allowlisted CLI inventory, skills overlay, Hermes HTTP `/health` probe, run-store + control-plane summaries, external-runner cards; snapshot includes **operator_connection** (derived CLI + HTTP + chat `gateway_mode` + freshness guidance; no new `hermes` argv); **Path C** placeholders for JSON-RPC/WebSocket/live-menu REST until upstream exists; raw CLI captures redacted; UI: `/command-center` + desktop **Settings → HAM + Hermes setup** strip; team operator story: `docs/TEAM_HERMES_STATUS.md` |
| Workspace UI | `frontend/` (Vite + React), `desktop/` (Electron shell) | Extracted workspace; TypeScript types aligned with persisted run / bridge shapes; optional **Clerk** for chat JWT; **execution mode** routing + Bridge browser adapters (`src/ham/execution_mode.py`, `src/bridge/browser_*.py`). **Workbench builder**: chat scaffold → **ZIP artifact** (`builder-artifact://`) + **auto cloud runtime job** (idempotent) when experiments/provider gates pass. Builder runtime now includes **B2 sandbox foundation**: provider-neutral sandbox contract + `sandbox_provider` dry-run/fake-provider lifecycle that can create cloud-mode runtime sessions and proxy-only preview endpoints without live provider calls. **Preview-status** remains cloud-oriented when source exists (localhost/local run profile remain **Advanced** only). **Desktop** (`desktop/README.md`): **Windows** installers via `npm run pack:win*`; **Linux `.deb`/AppImage packaging targets were removed** (dev: `npm start`). `window.hamDesktop.localControl` exposes Local Control policy/audit/kill-switch, sidecar lifecycle, and **main-process** managed-browser IPC (MVP/real CDP) where enabled — separate from Ham API **`/api/browser*`.** **Workspace chat** does not run the removed **GoHAM-mode** managed-browser/chat loop (`POST /api/goham/planner` stays API-only). See `docs/desktop/local_control_v1.md`; `docs/goham/browser_smoke.md` for historical/future notes. |
| Chat operator + identity gate | `src/api/chat.py`, `src/ham/chat_operator.py`, `src/ham/clerk_auth.py`, `src/ham/clerk_policy.py`, `src/ham/clerk_email_access.py`, `src/ham/operator_audit.py` | Server-side operator before LLM; optional Clerk JWT (`HAM_CLERK_REQUIRE_AUTH` or `HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS`, `CLERK_JWT_ISSUER`), `ham:*` permission checks, optional HAM allowlist email/domain defense-in-depth; append-only audit in HAM JSONL — **not** Clerk metadata; Cursor API key unchanged; chat sessions persist via **`HAM_CHAT_SESSION_STORE`** (default **sqlite**, optional **firestore** / **memory**) and, when **`workspace_id`** is supplied, list/get/export paths scope rows to that workspace and the resolved user id |
| HAM-on-X social agent | `src/ham/ham_x/`, `docs/ham-x-agent/`, `src/api/social.py`, `src/ham/social_persona/`, `frontend/src/features/hermes-workspace/screens/social/` | **Phase 4C Reactive Batch Mode + Social TD-1/SP-3/TD-3A:** Phase 2B remains execution-disconnected, Phase 3A `goham_controller.py` remains dry-run-only, and Phase 3B `goham_live_controller.py` remains original-post-only. Phase 4A `goham_reactive.py` still classifies prepared/read-only inbound mentions/comments into dry-run review/exception records. Phase 4B `reactive_reply_executor.py` / `goham_reactive_live.py` remain a separate one-shot reply canary. Phase 4B.1 `goham_reactive_inbox.py` discovers mentions/comments and returns automatic reply targets without executing. Phase 4C adds opt-in, dry-run-first `goham_reactive_batch.py` for bounded multi-candidate processing with per-item policy/governor rechecks, existing reactive rolling caps/cooldowns, per-reply journal rows, provider failure stops, and no retries. Social TD-1 adds read-only Telegram/Discord readiness, capabilities, and setup checklist endpoints backed by safe Hermes gateway env/status-file signals, plus read-only workspace panels. Social SP-1/SP-3 adds the read-only `ham-canonical` persona registry, deterministic digest, bounded persona API, docs, Persona panel, and persona id/version/digest protection in X preview/apply digests. Social TD-2A strengthens Telegram readiness with safe token/allowlist/home/test-group/mode presence booleans plus bounded Hermes gateway runtime/platform-state validation. Social TD-2B adds `POST /api/social/providers/telegram/messages/preview` for deterministic, persona-protected, masked-target Telegram dry-run message previews with proposal digests. Social TD-3A adds a narrow HAM-owned Telegram Bot API one-shot sender (`src/ham/social_telegram_send.py`), redacted delivery log (`src/ham/social_delivery_log.py`), and confirmed `POST /api/social/providers/telegram/messages/apply` gated by operator token, exact confirmation, recomputed preview digest, persona digest, server-side target resolution, and connected Hermes/Telegram readiness; no Telegram batch/reactive route, arbitrary target/text, broad Hermes `send_message` tool, gateway process controls, credential inputs, raw IDs, Hermes/Eliza export, or persona editing. Reactive budgets remain separate from broadcast caps; no scheduler, daemon, infinite loop, original posts, quotes, DMs, likes/follows, xurl mutation, manual canary, broadcast executor, or Phase 2B execution |
| Control plane runs (v1) | `src/persistence/control_plane_run.py`, `src/ham/cursor_agent_workflow.py`, `src/ham/droid_workflows/preview_launch.py`, `src/api/control_plane_runs.py` | **Durable** JSON per `ham_run_id` under `HAM_CONTROL_PLANE_RUNS_DIR` (default `~/.ham/control_plane_runs`): committed Cursor Cloud Agent + Factory Droid launches and Cursor status updates; **read** list/detail API (`/api/control-plane-runs*`) is factual only; **not** a mission graph, queue, or bridge `RunStore` |
| Managed Cloud Agent + mission record | `src/persistence/managed_mission.py`, `src/ham/managed_mission_wiring.py`, `src/ham/managed_mission_truth.py`, `src/api/cursor_settings.py`, `src/api/cursor_managed_*.py`, `src/ham/cursor_agent_workflow.py`, `src/ham/chat_operator.py`, Hermes Workspace (`WorkspaceManagedMissionsLivePanel`), `src/integrations/cursor_sdk_bridge_client.py` | Durable per-agent mission JSON + API read (observed lifecycle, deploy/Vercel last-seen); optional `project_id` on HAM launch for create-time `mission_deploy_approval_mode` snapshot; **Chat operator** can preview/launch Cursor Cloud Agent with `cursor_mission_handling: managed` — same managed prompt for digest/launch, `ManagedMission` row on successful API launch; mission **feed** projection: `HAM_CURSOR_SDK_BRIDGE_ENABLED=true` uses the live Cursor SDK bridge (`bridge.mjs`); unset/false falls back to REST projection (same route, honest `provider_projection.mode`); **Roadmap phases A–D (v1 slices):** `GET .../truth` observability table; `GET .../correlation` + optional embedded `ControlPlaneRun`; token-gated `POST .../hermes-advisory` (`HAM_MANAGED_MISSION_WRITE_TOKEN`) for capped `HermesReviewer` advisory fields only; token-gated `PATCH .../board` for operator `mission_board_state` lanes (`backlog`/`active`/`archive`, not a graph) with automatic active→archive on terminal lifecycle; Workspace detail surfaces truth + correlation + token field; **not** a mission queue or Hermes-to-Cursor action loop — see `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`, `docs/examples/managed_cloud_agent_phases/README.md` |
| Context engine | `src/memory_heist.py` | Hardened + tested (Phase 1/3 guardrails complete) |
| LLM routing | `src/llm_client.py` | Working |
| Critique MVP | `src/hermes_feedback.py` | Implemented (`HermesReviewer.evaluate()`), conservative fallback, tested |

**Interpretation rule:** "Target" defines architecture direction; "Current"
reports implementation reality. Do not treat transitional scaffolding as
architecture contract.

### Registries

The shipped registry surface includes `IntentProfile`, `ProfileRegistry`, `Selector`, `KeywordSelector`, and `DEFAULT_PROFILE_REGISTRY` in `src/registry/profiles.py`, plus `DroidRecord`, `DroidRegistry`, and `DEFAULT_DROID_REGISTRY` in `src/registry/droids.py` (builder and reviewer droids; pure-data records per registry conventions). `IntentProfile` records are pure data with `id`, `version`, `argv`, and `metadata` fields. The selection seam is a `Protocol` with one method (`select(prompt) -> str`) and currently has one default implementation (`KeywordSelector`).

The shipped backend registry surface is `ExecutionBackend`, `LocalDroidBackend`, `BackendRecord`, `BackendRegistry`, `DEFAULT_BACKEND_ID`, and `DEFAULT_BACKEND_REGISTRY` in `src/registry/backends.py`. `BackendRecord` follows the same pure-data Pydantic convention as `IntentProfile` (`id`, `version`, `metadata`, no methods). Runtime backend resolution currently uses hardcoded `DEFAULT_BACKEND_ID` against a single registered backend; per-intent backend selection is deferred.

Completed runs are now persisted as structured JSON at `.ham/runs/<timestamp>-<run_id>.json`. Persisted records include `run_id`, `created_at`, `profile_id`, `profile_version`, `backend_id`, `backend_version`, `prompt_summary`, `bridge_result`, and `hermes_review`. `run_id` is canonical from `bridge_result.run_id` (never regenerated); the timestamp in the filename is metadata for sort/collision only. The stdout `RUNTIME_RESULT` envelope shape remains unchanged, and persistence is additive. `BackendRegistry.get_record()` is now the first public backend-record accessor.

**Tests**: full `pytest` suite including registry, bridge, main loop, droid registry, API/CORS, control-plane catalog (skills + subagents + Hermes runtime skills Phase 1/2a) + UI action parsing, chat streaming + SQLite session store, project settings preview/apply/rollback (including **HAM agent profiles** / `agents` in `.ham/settings.json`), and persistence tests — run `pytest` for current counts (`pytest.ini` sets `pythonpath = .`; GitHub Actions runs `pytest` + frontend `tsc`).

**Next milestone**: finish B2 builder runtime from sandbox foundation to live provider integration (real sandbox create/upload/install/start + health-checked proxy preview readiness, still no secret/browser leakage). In parallel: stronger **UI-actions** marker recovery; continue Bridge-profile hardening. **Capability library** Phase 1 is shipped (saved `hermes:` / `capdir:` refs, token + audit, **Capabilities → My library** + **Skills** save — no install). Optional follow-on: **Phase 2** wire save UI to **Hermes skills** install (delegate to existing preview/apply). **Hermes gateway broker** Path B is shipped (`/command-center`, broker docs); optional follow-on: consume official Hermes **run** SSE from HAM-orchestrated runs only, and widen HTTP probes when `/health/detailed` is verified on target Hermes builds. **HAM agent builder** Slices 1–2 (persisted profiles) and **Slice 3** (compact **active agent guidance** injected into `/api/chat` / stream when `project_id` is sent — catalog descriptors only, no install/execution) are shipped. Expand allowlisted settings keys only with explicit review. (Context & Memory **settings preview/apply** UI is shipped; **`GET /api/cursor-subagents`** + chat prompt injection for review charters is shipped; **Hermes runtime skills** Phase 2a shared local install is shipped — profile-target install and broader topologies deferred.)

**Deferred:** FTS5 durable learning persistence, second orchestration harness,
architecture sprawl.

## Design Principles

1. **Agents don't freestyle** — every agent gets grounded context from
   memory_heist before it touches anything. No hallucinating about repo state.
2. **Separation of duties is enforced** — Hermes supervises and critiques;
   Droid executes and may self-orchestrate locally during execution.
3. **Learning compounds** — Hermes collects and applies learning signals over
   time; durable FTS5 persistence is a planned follow-up.
4. **Models are disposable** — swap providers, swap models, swap pricing.
   The architecture doesn't care which LLM is behind the API.
5. **Local-first** — no cloud dependencies for context, memory, or learning.
   Everything runs against the local filesystem and local DBs.
