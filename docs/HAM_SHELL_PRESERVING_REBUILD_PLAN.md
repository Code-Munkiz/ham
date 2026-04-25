# HAM v3 Shell-Preserving Rebuild Plan

## Intent and boundary

This plan defines a controlled HAM UI rebuild that preserves shell, API contracts, Cloud Agent pathways, auth boundaries, and deploy/secrets wiring while replacing route internals and stale presentation layers.

## 1) Preserved core

These files/modules are preservation-critical because they anchor shell, theme, auth, API boundaries, Cloud Agent behavior, chat, voice dictation, and deploy/secrets handling.

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

### Chat + voice + Cloud Agent behavior seam (must remain behavior-compatible)

- `frontend/src/pages/Chat.tsx` — single owner of `/chat` workbench behavior, stream handling, Cloud Agent orchestration UI states.
- `frontend/src/components/chat/CloudAgentLaunchModal.tsx` — managed/direct mission launch + attach semantics.
- `frontend/src/hooks/useManagedCloudAgentPoll.ts` — Cloud Agent status/review/readiness polling loop.
- `frontend/src/contexts/ManagedCloudAgentContext.tsx` — managed mission state contract for right-pane/UI.
- `frontend/src/components/chat/VoiceMessageInput.tsx` — voice controls and inline error rendering behavior.
- `frontend/src/hooks/useVoiceRecorder.ts` — device/permission handling and recorder lifecycle.
- `frontend/src/lib/ham/voiceRecordingErrors.ts` — user-safe recorder error mapping.

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

| file/path | current purpose | API dependency | risk level | safe replacement strategy |
|---|---|---|---|---|
| `frontend/src/pages/CommandCenter.tsx` | tabbed broker snapshot/operator overview page | `fetchHermesGatewaySnapshot`, `fetchModelsCatalog` | Medium | Rebuild entire page composition; retain same data fetches and status semantics |
| `frontend/src/pages/Activity.tsx` | activity stream view with live->demo fallback | `fetchHermesGatewaySnapshot` | Medium | Replace list/timeline UI; keep live poll cadence and fallback honesty |
| `frontend/src/pages/HermesSkills.tsx` | skills catalog/live overlay/install preview/apply surface | multiple `fetchHermesSkills*`, install preview/apply calls | High | Keep endpoint usage + write-token gating; replace layout/cards/panel internals |
| `frontend/src/pages/AgentBuilder.tsx` | project-scoped HAM agent profile editor | `fetchContextEngine`, `ensureProjectIdForWorkspaceRoot`, `fetchProjectAgents`, `postSettingsPreview/apply` | High | Rebuild editor UX while preserving preview/apply workflow and token-gated save |
| `frontend/src/pages/Runs.tsx` | run history list presentation | `GET /api/runs` via `apiUrl` | Low | Replace table/list visuals freely; keep list fetch and navigation to details |
| `frontend/src/components/workspace/UnifiedSettings.tsx` | settings IA and many panel internals | `fetchCursorCredentialsStatus`, `saveCursorApiKey`, `fetchContextEngine`, `postSettingsPreview/apply`, etc. | High | Keep panel responsibilities and API calls; redesign nav/content system behind same settings route |
| `frontend/src/components/war-room/*` | chat right-pane panels/split visuals | reads chat + managed cloud agent state | Medium | Replace panel components while preserving data contracts from `Chat.tsx` context |
| `frontend/src/components/chat/*` (presentation layer except behavior-critical adapters) | message rows/composer auxiliaries/launch dialogs | chat/Cloud Agent APIs via parent | High | Rebuild components with compatibility wrappers around existing callbacks/props |
| `frontend/src/pages/HermesHub.tsx` | legacy hub surface | `fetchHermesHubSnapshot` and related read APIs | Low | Replace or de-emphasize visuals, keep route live and read-only contract |
| `frontend/src/pages/Analytics.tsx`, `frontend/src/pages/Logs.tsx`, `frontend/src/pages/HamShop.tsx` | secondary operational surfaces | mixed read APIs and placeholders | Medium | Rebuild progressively; preserve route availability and any active API dependencies |

## 3) Compatibility adapters to keep during migration

Use adapters to decouple new UI from existing backend contracts:

- **Chat transport adapter:** continue using `postChatStream` and `postChatTranscribe` from `api.ts`; do not introduce direct fetches to external gateways.
- **Cloud Agent adapter:** continue using `launchCursorAgent`, `fetchCursorAgent`, `fetchCursorAgentConversation`, `fetchManagedMissionForAgent`, deploy hook/approval helpers.
- **Settings write adapter:** keep preview/apply flows through `postSettingsPreview` and `postSettingsApply` with server token checks.
- **Skills adapter:** keep Hermes skills and capability directory/library calls in `api.ts`; new UI should call wrapper hooks/services instead of raw endpoint strings.
- **Auth adapter:** preserve Clerk token bridging (`ClerkAccessBridge` + `mergeClerkAuthBearerIfNeeded`) and restricted deployment behavior.
- **Desktop/web adapter:** keep `desktopConfig` + `getApiBase` branch logic unchanged during UX migration.

## 4) Route-by-route contract

### `/chat`

- **Current component:** `frontend/src/pages/Chat.tsx`
- **Current API dependencies:** `postChatStream`, `postChatTranscribe`, `fetchModelsCatalog`, `fetchChatSessions`, `fetchChatSession`, managed Cloud Agent APIs (`launchCursorAgent`, `postCursorAgentSync`, deploy hook/approval/status calls), project metadata APIs.
- **Must-preserve behavior:** stream completion UX; voice dictation with clean no-mic inline errors; no auto-send after transcription; Cloud Agent launch/attach/status loop; auth-gated API calls via HAM.
- **Safe rebuild approach:** replace message/workbench visual system and panel composition while retaining current event/state handlers and API adapters.
- **Manual smoke test:** send prompt and verify stream completes; no-mic voice error appears inline; mic-enabled dictation inserts text without auto-send; managed Cloud Agent launch/status still updates.

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

## 5) Cloud Agent preservation checklist

The following must continue working throughout migration:

- [ ] Launch new Cloud Agent missions from chat (`launchCursorAgent` path).
- [ ] Attach/re-attach existing mission IDs.
- [ ] Poll status and conversation (`fetchCursorAgent`, `fetchCursorAgentConversation`).
- [ ] Managed mission correlation (`fetchManagedMissionForAgent`) and status line rendering.
- [ ] Deploy hook status + trigger path remains server-mediated.
- [ ] Deploy approval status/decision flow remains token/role-safe.
- [ ] No browser-side secrets for Cursor, Vercel, or gateway keys.
- [ ] Browser only calls HAM FastAPI endpoints; no direct upstream gateway calls.

## 6) Theme/shell preservation checklist

Preserve these files/tokens/chrome contracts to maintain HAM visual identity:

- [ ] `frontend/src/index.css` token block (`--color-*`, industrial palette, typography tokens).
- [ ] `frontend/src/components/layout/AppLayout.tsx` shell frame, control panel overlay, bottom utility strip.
- [ ] `frontend/src/components/layout/NavRail.tsx` route icons/chrome behavior and diagnostics grouping.
- [ ] `frontend/src/components/layout/Header.tsx` top status/navigation feel on non-chat routes.
- [ ] `frontend/src/App.tsx` route table + providers + desktop/web router split behavior.
- [ ] `frontend/src/main.tsx` + global CSS import pipeline.
- [ ] Chat composer visual baseline in `/chat` (industrial/dark composition language) even as internals are refreshed.

## 7) Proposed rebuild phases

### Phase 0 — Safety net

- Create rollback tag before any implementation migration commit.
- Lock preserved-core file list in PR description/checklist.
- No implementation changes; docs/inventory/tests only.

### Phase 1 — New Chat/Operator Workspace inside existing shell

- Keep `/chat` route, stream transport, and voice transcription contracts unchanged.
- Rebuild message/workbench/operator presentation components only.
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

## 8) Stop conditions

Stop immediately and require explicit review if a proposed change would:

- Delete or bypass `frontend/src/lib/ham/api.ts`.
- Expose API keys/secrets to browser code.
- Introduce direct browser calls to Hermes gateway/upstream hosts.
- Remove or disable Cloud Agent launch/status behavior.
- Break `/chat` streaming or voice dictation flow.
- Replace global shell/theme foundations (`App.tsx`, layout shell, `index.css` tokens) without approval.
- Add terminal/process/file-system/hermes-proxy capabilities.

## 9) Acceptance test matrix (must remain green during migration)

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

