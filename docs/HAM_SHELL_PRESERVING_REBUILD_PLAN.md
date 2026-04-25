# HAM v3 Shell-Preserving Rebuild Plan

## Intent and boundary

This plan defines a controlled HAM UI rebuild that preserves shell, API contracts, Cloud Agent pathways, auth boundaries, and deploy/secrets wiring while replacing route internals and stale presentation layers.

Voice correction in this revision:

- Current HAM voice frontend implementation is classified as replaceable (not sacred).
- Backend transcription seam remains temporarily preserved until replacement voice is adapted, tested, and approved.

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

- `frontend/src/pages/Chat.tsx` — single owner of `/chat` workbench behavior, stream handling, Cloud Agent orchestration UI states.
- `frontend/src/components/chat/CloudAgentLaunchModal.tsx` — managed/direct mission launch + attach semantics.
- `frontend/src/hooks/useManagedCloudAgentPoll.ts` — Cloud Agent status/review/readiness polling loop.
- `frontend/src/contexts/ManagedCloudAgentContext.tsx` — managed mission state contract for right-pane/UI.
### Voice backend seam (preserve temporarily)

- `POST /api/chat/transcribe` in backend routes — preserve until replacement voice path is proven.
- `HAM_TRANSCRIPTION_API_KEY`, `HAM_TRANSCRIPTION_PROVIDER`, `HAM_TRANSCRIPTION_MODEL` — keep server-side secret/env boundary.
- `scripts/seed_ham_transcription_api_key.sh` — maintain secret bootstrap path.
- `scripts/deploy_ham_api_cloud_run.sh` secret mount for `HAM_TRANSCRIPTION_API_KEY`.
- `requirements.txt` multipart/transcription route dependencies (for example `python-multipart`) while `/api/chat/transcribe` remains active.

### Voice frontend classification note

- Current HAM voice frontend implementation is replaceable and should not block the rebuild.

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

- `docs/HERMES_GATEWAY_CONTRACT.md`
- `docs/HERMES_WORKSPACE_FEATURE_MATRIX.md`

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
| `frontend/src/components/war-room/*` | chat right-pane panels/split visuals | Workspace operator pane composition | reads chat + managed cloud agent state | New pane stack preserves managed mission context behaviors | Medium |
| `frontend/src/components/chat/*` (presentation layer except behavior-critical adapters) | message rows/composer auxiliaries/launch dialogs | Workspace chat components adapted to HAM data model | chat/Cloud Agent APIs via parent | New components preserve send/stream/Cloud Agent semantics | High |
| `frontend/src/pages/HermesHub.tsx` | legacy hub surface | Simplified workspace status hub | `fetchHermesHubSnapshot` and related read APIs | Replacement preserves route availability + read-only honesty | Low |
| `frontend/src/pages/Analytics.tsx`, `frontend/src/pages/Logs.tsx`, `frontend/src/pages/HamShop.tsx` | secondary operational surfaces | Workspace-inspired dashboards/modules | mixed read APIs and placeholders | Route/API parity validated post-rebuild | Medium |
| `frontend/src/components/chat/VoiceMessageInput.tsx` | current voice button/recording UI | Workspace-inspired voice controls and state machine | uses `postChatTranscribe` through `/chat` wiring | Replacement voice UI passes no-mic + working-mic smoke on HAM seam | High |
| `frontend/src/components/chat/VoiceMessageInput.css` | voice-specific styling | Workspace voice visual system | none directly (style only) | New voice styling in place and accessible in composer | Low |
| `frontend/src/hooks/useVoiceRecorder.ts` | media recorder lifecycle and errors | Workspace voice capture logic adapted to HAM constraints | frontend-only media capture feeding transcribe path | Replacement recorder handles permission/no-device/abort correctly | High |
| `frontend/src/lib/ham/voiceRecordingErrors.ts` | maps media errors to user text | Workspace-aligned error copy map | frontend-only; affects no-mic UX and permission messaging | New mapping preserves clear inline user messaging | Medium |
| voice wiring in `frontend/src/pages/Chat.tsx` | composer/transcribe integration path | Workspace voice orchestration inside new chat UX | `postChatTranscribe` (`/api/chat/transcribe`) | Replacement voice path integrated, no auto-send regressions, send-state gating preserved | High |

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

## 5) Route-by-route contract

### `/chat`

- **Current component:** `frontend/src/pages/Chat.tsx`
- **Current API dependencies:** `postChatStream`, `postChatTranscribe`, `fetchModelsCatalog`, `fetchChatSessions`, `fetchChatSession`, managed Cloud Agent APIs (`launchCursorAgent`, `postCursorAgentSync`, deploy hook/approval/status calls), project metadata APIs.
- **Must-preserve behavior:** preserve `/chat` route, stream completion UX, typed chat send behavior, Cloud Agent launch/attach/status loop, auth-gated API calls via HAM.
- **Safe rebuild approach:** replace composer/message/workspace UI and replace current HAM voice implementation with Workspace-inspired voice while preserving stream and Cloud Agent adapter seams.
- **Manual smoke test:** send prompt and verify stream completes; no-mic voice path shows clean inline error; mic-enabled dictation inserts text without auto-send; send-state gating holds during transcription; managed Cloud Agent launch/status still updates.

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

## 6) Cloud Agent preservation checklist

The following must continue working throughout migration:

- [ ] Launch new Cloud Agent missions from chat (`launchCursorAgent` path).
- [ ] Attach/re-attach existing mission IDs.
- [ ] Poll status and conversation (`fetchCursorAgent`, `fetchCursorAgentConversation`).
- [ ] Managed mission correlation (`fetchManagedMissionForAgent`) and status line rendering.
- [ ] Deploy hook status + trigger path remains server-mediated.
- [ ] Deploy approval status/decision flow remains token/role-safe.
- [ ] No browser-side secrets for Cursor, Vercel, or gateway keys.
- [ ] Browser only calls HAM FastAPI endpoints; no direct upstream gateway calls.

## 7) Theme/shell preservation checklist

Preserve these files/tokens/chrome contracts to maintain HAM visual identity:

- [ ] `frontend/src/index.css` token block (`--color-*`, industrial palette, typography tokens).
- [ ] `frontend/src/components/layout/AppLayout.tsx` shell frame, control panel overlay, bottom utility strip.
- [ ] `frontend/src/components/layout/NavRail.tsx` route icons/chrome behavior and diagnostics grouping.
- [ ] `frontend/src/components/layout/Header.tsx` top status/navigation feel on non-chat routes.
- [ ] `frontend/src/App.tsx` route table + providers + desktop/web router split behavior.
- [ ] `frontend/src/main.tsx` + global CSS import pipeline.
- [ ] Chat composer visual baseline in `/chat` (industrial/dark composition language) even as internals are refreshed.

## 8) Proposed rebuild phases

### Phase 0 — Safety net

- Create rollback tag before any implementation migration commit.
- Lock preserved-core file list in PR description/checklist.
- Classify current HAM voice frontend implementation as replaceable.
- No implementation changes; docs/inventory/tests only.

### Phase 1 — New Chat/Operator Workspace inside existing shell

- Keep `/chat` route and stream transport contract unchanged (`POST /api/chat/stream`).
- Rebuild message/workbench/operator presentation components.
- Replace current HAM voice frontend with Workspace-inspired voice UI/flows.
- Adapt replacement voice to HAM backend transcription seam.
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

## 9) Stop conditions

Stop immediately and require explicit review if a proposed change would:

- Delete or bypass `frontend/src/lib/ham/api.ts`.
- Expose API keys/secrets to browser code.
- Expose transcription API keys to browser code.
- Introduce direct browser calls to transcription providers.
- Introduce direct browser calls to Hermes gateway/upstream hosts.
- Remove or disable Cloud Agent launch/status behavior.
- Delete backend transcription route before replacement voice is proven.
- Delete Secret Manager wiring before replacement voice is proven.
- Break `/chat` route or stream behavior.
- Replace global shell/theme foundations (`App.tsx`, layout shell, `index.css` tokens) without approval.
- Add terminal/process/file-system/hermes-proxy capabilities.

## 10) Acceptance test matrix (must remain green during migration)

### Required command checks

- `git status --short`
- `cd frontend && npm run build && cd ..`
- `python -m pytest tests/test_chat_stream.py tests/test_nous_gateway_http_fallback.py`

### Required manual smoke checks

- **Chat stream:** `/chat` send prompt, confirm stream completes.
- **Voice no-mic:** mic blocked/unavailable shows clean inline error; no overlay regression.
- **Voice with mic:** record->stop inserts transcript in composer; no auto-send; send disabled during transcribe.
- **Cloud Agent:** launch/attach mission, status updates, managed polling, deploy approval/deploy hook checks.
- **Route availability:** `/chat`, `/command-center`, `/activity`, `/skills`, `/agents`, `/runs`, `/settings` all load.

## 11) Temporary backend voice/transcription seams to preserve

Until replacement voice is fully adapted and proven:

- Preserve `POST /api/chat/transcribe`.
- Preserve `HAM_TRANSCRIPTION_API_KEY`, `HAM_TRANSCRIPTION_PROVIDER`, `HAM_TRANSCRIPTION_MODEL`.
- Preserve Secret Manager seed/mount workflow (`scripts/seed_ham_transcription_api_key.sh`, `scripts/deploy_ham_api_cloud_run.sh`).
- Preserve multipart backend support in `requirements.txt` as long as transcription upload route remains active.

