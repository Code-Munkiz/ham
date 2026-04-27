# HAM v3 Shell-Preserving Rebuild Plan

## Intent and boundary

This plan defines a controlled HAM UI rebuild that preserves shell, API contracts, Cloud Agent pathways, auth boundaries, and deploy/secrets wiring while replacing route internals and stale presentation layers.

Voice correction in this revision:

- Current HAM voice frontend implementation is classified as replaceable (not sacred).
- Backend transcription seam remains temporarily preserved until replacement voice is adapted, tested, and approved.

## Runtime strategy

This section names the product path for the shell-preserving rebuild. It is planning language only: no second product mode, no runtime switch in the UI, and no governed-runtime implementation in this plan.

### Default Workspace Runtime

This is the **only active runtime** for the current build and the **default product path**.

It should deliver a **Hermes Workspace–style operator experience** while staying inside HAM’s shell: workspace-oriented layout, responsive composer, voice/dictation UX, attachment UX, sessions/sidebar/panels, and settings/config surfaces, with a mobile, web, and desktop–friendly presentation. Surfaces that resemble terminal, files, or process control may be considered **only when explicitly approved** in a later scope decision; they are not part of this plan’s deliverables by default.

The current HAM `/chat` internals, current voice frontend, and current composer/attachment **presentation** are replaceable. The **Default Workspace Runtime** must still preserve HAM’s operational foundation:

- HAM shell, layout, theme, and color system.
- `frontend/src/lib/ham/api.ts` as the **only** browser → HAM API seam.
- Clerk, auth, and session behavior.
- Cloud Agent launch, status, and managed mission flows.
- Cloud Run, FastAPI, and GCP/Secret Manager boundaries.
- No browser-side secrets; no direct browser calls from client code to Hermes VM, Cursor, OpenAI, transcription providers, or other upstream APIs.

In short: **build the default Workspace experience in presentation and operator UX; do not break HAM’s security and integration boundary.**

### Future Governed Runtime Extension Point

The **governed / policy-heavy alternative** to the default path is **not** active today, **not** implemented today, and **not** visible in the UI today.

A future user- or org-specific governed runtime may add stricter policy around terminal, files, and process behavior; scoped filesystem; audited command execution; org/user-specific restrictions; stronger RBAC; and alternate provider/runtime behavior. **Do not build that now.**

The architecture should still leave a **clean extension point** so a future governed runtime can be added **without throwing away the Operator Workspace UI**. Prefer introducing that later through a small **runtime / capability / transport seam** (see Design guidance) rather than scattering `if governed` checks through presentation components.

**Do not build a dual-runtime product today**—only one product path ships; the “extension point” is a seam for later, not a second shipped mode.

### Design guidance for Phase 1A

- **Avoid** baking provider- or environment-specific assumptions (which gateway, which transport shape, which “mode”) directly into presentational components. Keep them in hooks, adapters, or a thin context that can swap implementation later without rewriting the whole chat shell.
- Where it helps, future-facing abstractions can use **neutral** names, for example: `workspaceRuntime`, `operatorRuntime`, `workspaceCapabilities`, `workspaceTransport`, `runtimeCapabilities`. **Do not overbuild** a framework; a few well-placed types or a single context is enough for the seam—no parallel abstraction layer for its own sake.
- **Build the Default Workspace Runtime now.** **Leave a clean seam** for a future governed runtime later. **Do not** implement two runtimes, two transports, or admin toggles in this phase unless explicitly re-scoped.

### Excluded from current scope (planning guardrails; do not implement in this plan)

The following are **out of scope** for this plan update and for the rebuild phases it describes, unless a separate, explicit decision adds them later:

- Runtime toggle UI, admin policy UI, or “governed vs default” product chrome.
- Governed terminal, governed filesystem, generic upstream proxy, or new browser-side PWA/service-worker stacks.
- New backend endpoints, new secrets, or xterm/PTY/terminal implementation.
- Any pattern that **duplicates** upstream Hermes Workspace server routes (for example ad hoc `/api/send-stream`–style BFFs in the **browser** contract) instead of HAM’s existing FastAPI and `api.ts` patterns.

## Memory Heist / Context Engine placement

**Memory Heist** (Context Engine) is the **Operator Workspace memory and context** capability. It is not a separate sidecar app, and it should **not** be implemented by copy-pasting Hermes Workspace memory UI or calling upstream memory routes from the browser.

It should sit **behind HAM-owned adapters** and feed:

- chat context preview
- Cloud Agent mission context bundles
- skills/capability context
- settings/config context review
- future file/terminal/process policy context (only when that scope is approved)

**Phase 1A.1 (initial) scope:** reserve **UI space and seams** for this capability (placeholders, layout hooks, or non-functional affordances) only. **Full Memory Heist wiring** is a **later phase** after `/chat` stream parity and Cloud Agent reachability are proven.

**Required boundary:**

- Browser calls **HAM only** (through `api.ts` and HAM FastAPI; no new browser→upstream memory endpoints).
- **No** raw upstream memory routes or provider memory APIs from the client.
- **No** unaudited or silent browser-side context injection into prompts, missions, or settings.
- Memory **writes/updates** go through HAM’s existing **preview/apply**, explicit user confirmation, or other audited server-mediated flows where applicable—not ad hoc client-only mutation.

## 1) Preserved core

These files/modules are preservation-critical because they anchor shell, theme, auth, API boundaries, Cloud Agent behavior, chat stream behavior, and deploy/secrets handling.

### Frontend shell, routing, theme, and runtime boundaries

- `frontend/src/App.tsx` — route ownership, Clerk + ThemeProvider, Agent/Workspace providers, desktop/web router split.
- `frontend/src/main.tsx` — app bootstrap and global stylesheet entry.
- `frontend/src/index.css` — global design tokens, color palette, typography, theme primitives.
- `frontend/src/components/layout/AppLayout.tsx` — shell chrome, global control panel, footer strip, toasts, route containment.
- `frontend/src/components/layout/NavRail.tsx` — primary nav route availability and diagnostics menu structure.
- `frontend/src/components/layout/Header.tsx` — top bar behavior and route context chrome.
- `frontend/src/lib/ham/desktopConfig.ts` — desktop shell detection + HashRouter/API base controls.
- `frontend/src/lib/ham/publicAssets.ts` (indirect nav/logo dependency) — stable asset URL resolution.

### Frontend auth and API seam

- `frontend/src/lib/ham/api.ts` — canonical browser->HAM API contract layer; includes chat/stream/transcribe, Cloud Agent launch/status, settings/capabilities, and auth header mediation.
- `frontend/src/lib/ham/ClerkAccessBridge.tsx` — Clerk session propagation, deployment access probe, and restricted-banner state.
- `frontend/src/lib/ham/clerkSession.ts` — registered token getter bridge used by `api.ts`.
- `frontend/src/lib/ham/AgentContext.tsx` and `frontend/src/lib/ham/WorkspaceContext.tsx` — global shell behavior/state dependencies.

### Chat stream + Cloud Agent behavior seam (must remain behavior-compatible)

- `/chat` → `/workspace/chat` redirect — preserve typed chat send, stream handling, and operator payloads on **`POST /api/chat`** / **`/api/chat/stream`** (Hermes **`WorkspaceChatScreen`** is the product client).
- Cloud Agent **API** contract — managed/direct mission launch + attach semantics, mission polling, deploy approval/deploy hook remain on the server; dedicated legacy War Room panels were **removed Batch 2A** (re-home UX in Workspace/Command Center as needed).
### Voice backend seam (preserve temporarily)

- `POST /api/chat/transcribe` in backend routes — preserve until replacement voice path is proven.
- `HAM_TRANSCRIPTION_API_KEY`, `HAM_TRANSCRIPTION_PROVIDER`, `HAM_TRANSCRIPTION_MODEL` — keep server-side secret/env boundary.
- `scripts/seed_ham_transcription_api_key.sh` — maintain secret bootstrap path.
- `scripts/deploy_ham_api_cloud_run.sh` secret mount for `HAM_TRANSCRIPTION_API_KEY`.
- `requirements.txt` multipart/transcription route dependencies (for example `python-multipart`) while `/api/chat/transcribe` remains active.

### Voice frontend classification note

- Voice UX lives in Hermes Workspace composer (`WorkspaceChatScreen` / `WorkspaceChatComposer`) using **`postChatTranscribe`**; legacy `Chat.tsx` wiring was removed **Batch 2A**.

### Env/config handling (frontend)

- `frontend/.env.example` — operator-facing env contract reference.
- `frontend/vite.config.ts` — dev proxy behavior and build assumptions.
- `frontend/package.json` (and lockfile) — build/runtime contract surface.

### Backend/API and integration boundary (must stay authoritative)

- `src/api/*` (especially `chat.py`, `server.py`, `hermes_gateway.py`, `cursor_*`, `project_settings.py`, `hermes_skills.py`, `capability_*`, `control_plane_runs.py`) — server routes/contracts.
- `src/integrations/*` (notably `nous_gateway_client.py`, `cursor_cloud_client.py`, `vercel_deployments_client.py`) — upstream mediation layer and outbound adapters.

### Deploy + secret wiring

- `scripts/deploy_ham_api_cloud_run.sh`
- `scripts/render_cloud_run_env.py`
- `scripts/seed_ham_transcription_api_key.sh`
- Cloud Run + Secret Manager conventions referenced by those scripts.

### Contract docs to preserve during rebuild

These planning and runtime contract documents should stay current and should not be dropped or silently contradicted by UI work. If the same content ever appears under a different path or casing, treat it as the same contract (today the repo has root-level `SWARM.md`; a lowercase `swarm.md` would be equivalent in intent).

- `docs/HERMES_GATEWAY_CONTRACT.md`
- `docs/HERMES_WORKSPACE_FEATURE_MATRIX.md`
- `docs/HAM_SHELL_PRESERVING_REBUILD_PLAN.md` (this plan)
- `SWARM.md` (repo root) — multi-agent / swarm planning and operator runtime contract; also reference as `swarm.md` if that casing is introduced elsewhere.

## 2) Replace candidates

The following areas are safe to aggressively redesign as long as route/API contract behavior remains compatible.

| file/path | current purpose | replacement target from Hermes Workspace | API dependency | safe removal condition | risk level |
|---|---|---|---|---|---|
| `frontend/src/pages/CommandCenter.tsx` | tabbed broker snapshot/operator overview page | Workspace command center shell with HAM broker cards | `fetchHermesGatewaySnapshot`, `fetchModelsCatalog` | New Command Center renders snapshot parity and refresh/poll behavior | Medium |
| `frontend/src/pages/Activity.tsx` | activity stream view with live->demo fallback | Workspace activity timeline styling and grouping | `fetchHermesGatewaySnapshot` | New activity view preserves live/fallback behavior and source/level tags | Medium |
| `frontend/src/pages/HermesSkills.tsx` | skills catalog/live overlay/install preview/apply surface | Workspace capability/skills explorer adapted to HAM | multiple `fetchHermesSkills*`, install preview/apply calls | New skills UX keeps token-gated install preview/apply semantics intact | High |
| `frontend/src/pages/AgentBuilder.tsx` | project-scoped HAM agent profile editor | Workspace-style agent cards/editor backed by HAM profile APIs | `fetchContextEngine`, `ensureProjectIdForWorkspaceRoot`, `fetchProjectAgents`, `postSettingsPreview/apply` | New agent editor preserves preview/apply gating and primary profile behavior | High |
| `frontend/src/pages/Runs.tsx` | run history list presentation | Workspace-inspired mission/runs table UX | `GET /api/runs` via `apiUrl` | Replacement runs view passes list/detail smoke tests | Low |
| `frontend/src/components/workspace/UnifiedSettings.tsx` | settings IA and many panel internals | Workspace-style settings panes with HAM adapters | `fetchCursorCredentialsStatus`, `saveCursorApiKey`, `fetchContextEngine`, `postSettingsPreview/apply`, etc. | New settings panes preserve write-token and auth constraints | High |
| ~~`frontend/src/components/war-room/*`~~ | *(removed Batch 2A)* | — | — | — | — |
| ~~`frontend/src/components/chat/*`~~ (legacy) | *(removed Batch 2A)* | Workspace chat components | `/api/chat` via Workspace | N/A | — |
| `frontend/src/pages/HermesHub.tsx` | legacy hub surface | Simplified workspace status hub | `fetchHermesHubSnapshot` and related read APIs | Replacement preserves route availability + read-only honesty | Low |
| `frontend/src/pages/Analytics.tsx`, `frontend/src/pages/Logs.tsx`, `frontend/src/pages/HamShop.tsx` | secondary operational surfaces | Workspace-inspired dashboards/modules | mixed read APIs and placeholders | Route/API parity validated post-rebuild | Medium |
| ~~`VoiceMessageInput`~~ | *(removed with legacy `components/chat`)* | Workspace composer mic UX | `postChatTranscribe` | See `WorkspaceChatScreen.tsx` | High |
| `frontend/src/hooks/useVoiceRecorder.ts` | media recorder lifecycle and errors | Workspace voice capture logic adapted to HAM constraints | frontend-only media capture feeding transcribe path | Replacement recorder handles permission/no-device/abort correctly | High |
| `frontend/src/lib/ham/voiceRecordingErrors.ts` | maps media errors to user text | Workspace-aligned error copy map | frontend-only; affects no-mic UX and permission messaging | New mapping preserves clear inline user messaging | Medium |
| Workspace chat voice | composer/transcribe integration | Hermes Workspace chat UX | `postChatTranscribe` (`/api/chat/transcribe`) | Preserve no-mic + working-mic smoke on HAM seam | High |

## 3) Compatibility adapters to keep during migration

Use adapters to decouple new UI from existing backend contracts:

- **Chat transport adapter:** continue using `postChatStream` and `postChatTranscribe` from `api.ts`; do not introduce direct fetches to external gateways.
- **Cloud Agent adapter:** continue using `launchCursorAgent`, `fetchCursorAgent`, `fetchCursorAgentConversation`, `fetchManagedMissionForAgent`, deploy hook/approval helpers.
- **Settings write adapter:** keep preview/apply flows through `postSettingsPreview` and `postSettingsApply` with server token checks.
- **Skills adapter:** keep Hermes skills and capability directory/library calls in `api.ts`; new UI should call wrapper hooks/services instead of raw endpoint strings.
- **Auth adapter:** preserve Clerk token bridging (`ClerkAccessBridge` + `mergeClerkAuthBearerIfNeeded`) and restricted deployment behavior.
- **Desktop/web adapter:** keep `desktopConfig` + `getApiBase` branch logic unchanged during UX migration.

## 4) Voice replacement strategy

- Current HAM voice frontend implementation can be removed.
- Replacement voice should be adapted from Hermes Workspace patterns/components.
- Replacement voice must continue using HAM backend/API boundaries.
- Never expose transcription provider keys to the browser.
- Prefer reusing `POST /api/chat/transcribe` unless a better HAM-owned backend route is explicitly designed and approved.
- Only delete backend transcription route/secrets after replacement voice is proven and an explicit migration decision is made.

## 5) Attachment replacement strategy

- Workspace-inspired attachment UI is allowed and expected.
- Browser attachment actions must still route to HAM-owned APIs only.
- Do not send browser uploads directly to OpenAI, transcription vendors, Cursor Cloud, Hermes gateway hosts, or any upstream provider.
- For attachment transport, choose one explicit path per feature before implementation:
  - UI-only preview with send disabled until backend support exists.
  - Reuse an existing HAM backend endpoint when contract-compatible.
  - Defer to a later phase that introduces a new HAM-owned backend route.
- Do not introduce new backend endpoints or new secrets in Phase 1A unless explicitly approved in a separate scope decision.

## 6) Route-by-route contract

### `/chat` (redirect) + `/workspace/chat`

- **Product chat:** `frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx` at **`/workspace/chat`**; **`/chat`** redirects (preserve query e.g. `?session=`).
- **Current API dependencies:** `postChatStream`, `postChatTranscribe`, `fetchModelsCatalog`, workspace session adapters, project metadata APIs (managed Cloud Agent dedicated UI removed Batch 2A — APIs remain on server).
- **Must-preserve behavior:** redirect, stream completion UX, typed chat send, auth-gated API calls via HAM.
- **Manual smoke test:** send prompt from Workspace chat and verify stream completes; voice/attachments follow Workspace composer rules.

### `/command-center`

- **Current component:** `frontend/src/pages/CommandCenter.tsx`
- **Current API dependencies:** `fetchHermesGatewaySnapshot`, `fetchModelsCatalog`
- **Must-preserve behavior:** read-only command center snapshot, honest capability/degraded labeling, refresh + poll.
- **Safe rebuild approach:** redesign cards/tabs/sections, preserve data model interpretation and links to downstream routes.
- **Manual smoke test:** page loads without errors, refresh works, key snapshot values populate.

### `/activity`

- **Current component:** `frontend/src/pages/Activity.tsx`
- **Current API dependencies:** `fetchHermesGatewaySnapshot`
- **Must-preserve behavior:** live API-derived events when available, explicit demo fallback behavior on failure.
- **Safe rebuild approach:** replace timeline visuals while preserving source/level semantics and fallback truthfulness.
- **Manual smoke test:** page loads, entries render with severity/source labels, no crash on transient API failure.

### `/skills`

- **Current component:** `frontend/src/pages/HermesSkills.tsx`
- **Current API dependencies:** Hermes skills catalog/capabilities/targets/live overlay + install preview/apply; capability directory panel dependencies.
- **Must-preserve behavior:** read-only catalog availability, capability signaling, install preview/apply token boundaries, no silent writes.
- **Safe rebuild approach:** modernize workspace layout and cards while preserving install safeguards and endpoint behavior.
- **Manual smoke test:** catalog loads, detail panel opens, preview works when supported, apply remains token-gated.

### `/agents`

- **Current component:** `frontend/src/pages/AgentBuilder.tsx`
- **Current API dependencies:** context engine/project registration, project agents fetch, settings write status, preview/apply.
- **Must-preserve behavior:** profile editing, primary profile semantics, skill id attachment, preview before apply, token-gated apply.
- **Safe rebuild approach:** replace builder visual/editor internals while keeping same persistence and validation flow.
- **Manual smoke test:** profile edit + preview works; apply remains blocked without token and succeeds with token.

### `/runs`

- **Current component:** `frontend/src/pages/Runs.tsx` (plus `RunDetail.tsx` for detail route)
- **Current API dependencies:** `GET /api/runs` and detail endpoints.
- **Must-preserve behavior:** run list visibility and navigation to run details.
- **Safe rebuild approach:** replace list/table aesthetics and filtering UI; maintain load/error/no-data behavior.
- **Manual smoke test:** runs list loads, selecting run opens detail route.

### `/settings`

- **Current component:** `frontend/src/pages/Settings.tsx` -> `frontend/src/components/workspace/UnifiedSettings.tsx`
- **Current API dependencies:** cursor credential status/save/clear/models; context engine; settings write status + preview/apply; project resolution.
- **Must-preserve behavior:** API key flows remain server-side, context/settings preview/apply preserve token gating, section navigation still stable via `?tab=`.
- **Safe rebuild approach:** rebuild section IA and visuals while preserving endpoint actions and access constraints.
- **Manual smoke test:** API keys panel loads, context panel loads, preview/apply flows still enforce write-token behavior.

## 7) Cloud Agent preservation checklist

The following must continue working throughout migration:

- [ ] Launch new Cloud Agent missions from chat (`launchCursorAgent` path).
- [ ] Attach/re-attach existing mission IDs.
- [ ] Poll status and conversation (`fetchCursorAgent`, `fetchCursorAgentConversation`).
- [ ] Managed mission correlation (`fetchManagedMissionForAgent`) and status line rendering.
- [ ] Deploy hook status + trigger path remains server-mediated.
- [ ] Deploy approval status/decision flow remains token/role-safe.
- [ ] No browser-side secrets for Cursor, Vercel, or gateway keys.
- [ ] Browser only calls HAM FastAPI endpoints; no direct upstream gateway calls.

## 8) Theme/shell preservation checklist

Preserve these files/tokens/chrome contracts to maintain HAM visual identity:

- [ ] `frontend/src/index.css` token block (`--color-*`, industrial palette, typography tokens).
- [ ] `frontend/src/components/layout/AppLayout.tsx` shell frame, control panel overlay, bottom utility strip.
- [ ] `frontend/src/components/layout/NavRail.tsx` route icons/chrome behavior and diagnostics grouping.
- [ ] `frontend/src/components/layout/Header.tsx` top status/navigation feel on non-chat routes.
- [ ] `frontend/src/App.tsx` route table + providers + desktop/web router split behavior.
- [ ] `frontend/src/main.tsx` + global CSS import pipeline.
- [ ] Chat composer visual baseline in `/chat` (industrial/dark composition language) even as internals are refreshed.

## 9) Proposed rebuild phases

### Phase 0 — Safety net

- Create rollback tag before any implementation migration commit.
- Lock preserved-core file list in PR description/checklist.
- Classify current HAM voice frontend implementation as replaceable.
- Classify current HAM attachment/composer presentation internals as replaceable.
- No implementation changes; docs/inventory/tests only.

### Phase 1 — New Chat/Operator Workspace inside existing shell

This phase implements the **Default Workspace Runtime** (see [Runtime strategy](#runtime-strategy)). It does not add a governed runtime, runtime toggles, or dual product paths.

#### Phase 1A.1 — Scaffold and parity

- Introduce `operator-workspace` feature module and mount it on `/chat`.
- Preserve typed send and streaming parity through `postChatStream`.
- Keep Cloud Agent launch/attach/status affordances reachable via existing adapters (direct reuse or compatibility bridge).
- Prefer thin hooks/adapters over embedding transport or policy assumptions in raw UI components (see [Design guidance for Phase 1A](#design-guidance-for-phase-1a)).
- Reserve **UI space / seams** for Memory Heist and context (see [Memory Heist / Context Engine placement](#memory-heist--context-engine-placement)); **do not** ship full context-engine wiring in 1A.1.
- Keep old chat path as a rollback-compatible fallback until parity checks pass.

#### Phase 1A.2 — Voice and attachment adaptation

- Keep `/chat` route and stream transport contract unchanged (`POST /api/chat/stream`).
- Replace current HAM voice frontend with Workspace-inspired voice UI/flows.
- Adapt replacement voice to HAM backend transcription seam (`POST /api/chat/transcribe`).
- Replace current attachment/composer UI with Workspace-inspired attachment affordances that remain HAM API mediated.
- Attachment sending must follow the explicit transport decision selected in this plan (UI-only disabled send, existing endpoint reuse, or deferred backend route).
- No browser-side secrets.
- Keep Cloud Agent launch/status wiring behaviorally identical.

### Phase 2 — Command Center / Agent surfaces

- Rebuild `/command-center`, `/activity`, `/agents` internals.
- Preserve Cloud Agent launch/status/deploy approval/deploy hook pathways.
- Keep all data through current `api.ts` adapters.

### Phase 3 — Skills/Runs/Settings cleanup

- Rebuild `/skills`, `/runs`, `/settings` internals.
- Keep route availability and endpoint contracts stable.
- Preserve token-gated write operations and auth/header behavior.

### Phase 4 — Delete retired components

- Only after replacement routes pass smoke tests and parity checks.
- Remove dead components in dedicated cleanup commits (no mixed feature changes).
- Delete backend transcription route only if replacement no longer needs it and secret migration is explicitly approved.
- Delete old attachment/voice frontend modules only after replacement flow passes smoke tests and no regressions are observed.

## 10) Stop conditions

Stop immediately and require explicit review if a proposed change would:

- Delete or bypass `frontend/src/lib/ham/api.ts`.
- Expose API keys/secrets to browser code.
- Expose transcription API keys to browser code.
- Introduce direct browser calls to transcription providers.
- Introduce direct browser uploads/calls to third-party attachment providers.
- Introduce direct browser calls to Cursor Cloud APIs.
- Introduce direct browser calls to Hermes gateway/upstream hosts.
- Remove or disable Cloud Agent launch/status behavior.
- Remove managed mission polling or deploy approval/deploy-hook reachability from `/chat`.
- Delete backend transcription route before replacement voice is proven.
- Delete Secret Manager wiring before replacement voice is proven.
- Break `/chat` route or stream behavior.
- Replace global shell/theme foundations (`App.tsx`, layout shell, `index.css` tokens) without approval.
- Add terminal/process/file-system/hermes-proxy capabilities.
- Add runtime toggle UI, governed-runtime product surface, or dual-runtime operator modes without an explicit re-scope (see [Runtime strategy](#runtime-strategy)).
- Wire Memory Heist or context to **raw upstream memory routes** from the browser, or add **unaudited browser-side context injection** into chat, Cloud Agent, or settings flows (see [Memory Heist / Context Engine placement](#memory-heist--context-engine-placement)).

## 11) Acceptance test matrix (must remain green during migration)

### Required command checks

- `git status --short`
- `cd frontend && npm run build && cd ..`
- `python -m pytest tests/test_chat_stream.py tests/test_nous_gateway_http_fallback.py`

### Required manual smoke checks

- **Chat stream:** `/chat` send prompt, confirm stream completes.
- **Voice no-mic:** mic blocked/unavailable shows clean inline error; no overlay regression.
- **Voice with mic:** record->stop inserts transcript in composer; no auto-send; send disabled during transcribe.
- **Attachments:** UI never calls upstream providers directly; send path is either HAM-backed or explicitly disabled pending backend support.
- **Cloud Agent:** launch/attach mission, status updates, managed polling, deploy approval/deploy hook checks.
- **Route availability:** `/chat`, `/command-center`, `/activity`, `/skills`, `/agents`, `/runs`, `/settings` all load.

## 12) Deletion candidates (post-parity only)

- ~~Legacy `components/chat/*` and `pages/Chat.tsx`~~ — **removed Batch 2A.**
- `frontend/src/hooks/useVoiceRecorder.ts` — still used by Workspace composer until replaced.
- `frontend/src/lib/ham/voiceRecordingErrors.ts` — keep while Workspace voice uses it.

## 13) Temporary backend voice/transcription seams to preserve

Until replacement voice is fully adapted and proven:

- Preserve `POST /api/chat/transcribe`.
- Preserve `HAM_TRANSCRIPTION_API_KEY`, `HAM_TRANSCRIPTION_PROVIDER`, `HAM_TRANSCRIPTION_MODEL`.
- Preserve Secret Manager seed/mount workflow (`scripts/seed_ham_transcription_api_key.sh`, `scripts/deploy_ham_api_cloud_run.sh`).
- Preserve multipart backend support in `requirements.txt` as long as transcription upload route remains active.

