# Phase 0: Hermes Workspace upstream inventory (HAM)

**Kind:** documentation only — no application code, no vendored source in HAM, no new routes, no new dependencies, no `api.ts` or backend changes.

**Purpose:** lock a reference upstream revision, name folders to lift or **re-implement** under HAM, and map same-origin API usage to HAM `api.ts` + FastAPI (never to upstream host from the browser).

---

## 1. Pinned upstream revision

| Field | Value |
|--------|--------|
| **Repository** | `https://github.com/outsourc-e/hermes-workspace` |
| **License** | MIT (verify on clone before copying files) |
| **Pinned commit (full SHA)** | `d2746363b4684a5fab1097e6f0e1a2fa142bac45` |
| **One-line log** | `fix(terminal): clear sessionId on PTY close/exit…` (as of local shallow clone) |
| **Re-pinning policy** | Re-run shallow clone to `main` and update this table before **vendor or large port**; do not auto-float. |

*Inventory generated from a read-only `git clone --depth 1` into a **temp** directory, not the HAM tree.*

---

## 2. Upstream top-level structure (what exists)

| Path (upstream) | Role for lift |
|------------------|---------------|
| `package.json` / `pnpm-lock.yaml` | **Do not** merge as HAM root — dependency set differs (TanStack Start, PWA, etc.). Use only as reference. |
| `vite.config.ts` | Reference only; HAM uses its own Vite config. |
| `src/` | **Primary** UI, routes, client stores. |
| `src/routes/` | TanStack Router + **many** `api/*` **server** route files — **not** portable to HAM as-is; they implement Node/TanStack handlers. **Do not** copy into HAM `frontend` bundle. |
| `src/server/` | Node/Hermes server integration — **not** copied; behavior must be re-expressed in FastAPI or **adapter-only** in the browser to `api.ts`. |
| `src/screens/` | Screen-level pages (chat, gateway, files, memory, skills, settings, etc.) — main **UI** lift candidates; **re-wire** fetches. |
| `src/components/`, `src/hooks/`, `src/stores/`, `src/lib/` | Shared UI/state — selective port or rewrite in HAM. |
| `public/` | PWA / assets — **do not** drop into HAM `public/` at root without namespacing (avoid SW override). |
| `scripts/`, `docker*`, `install.sh` | Ops only — not part of UI lift. |

---

## 3. Key upstream `src/` subfolders to adapt (files / behavior)

*High-level; exact file lists are large — treat `src/screens/chat/` and shell layout as **priority 1** for 1:1 UX.*

| Area | Primary upstream locations (indicative) | Lift notes |
|------|----------------------------------------|------------|
| **App shell / routing** | `src/router.tsx`, `src/routeTree.gen.ts`, `src/routes/*` (non-api) | Map to HAM `App.tsx` + a future `WorkspaceApp` + React Router, **not** TanStack file routes. |
| **Chat** | `src/screens/chat/*`, `use-streaming-message.ts` (`/api/send-stream`) | **Critical:** stream must go to `postChatStream` / HAM NDJSON, not `send-stream`. |
| **Sessions** | `chat-queries.ts`, `use-rename-session.ts`, `use-delete-session.ts`, `chat/sidebar` | Map to HAM `fetchChatSessions` / `fetchChatSession` semantics. |
| **Composer / models** | `chat-composer.tsx` (`/api/models`, `/api/hermes-proxy/...`, etc.) | Every `/api/*` call needs an **adapter** to existing HAM models/settings endpoints. |
| **Settings** | `src/routes/settings/*`, `src/screens/settings/*` | Map to `UnifiedSettings` / `api.ts` preview-apply, not `config-patch` as assumed upstream. |
| **Skills** | `src/routes/skills.tsx`, `src/screens/skills/*` | Map to HAM hermes-skills + capability library; different contracts. |
| **Memory** | `src/screens/memory/*`, `src/routes/memory.tsx` | **Defer** or read-only; no upstream memory URLs in browser. |
| **Files / terminal** | `src/screens/files/*`, `src/routes/terminal.tsx`, `src/routes/api/terminal-*.ts` | **Deferred** in HAM until separate policy. |
| **Gateway / conductor** | `src/screens/gateway/*` | Orchestration surface — align with HAM “command” surfaces later; not Phase 1. |
| **Tasks / dashboard** | `src/stores/task-store.ts`, `dashboard-screen.tsx` | often `/api/tasks`, `/api/sessions` — **gap list** for FastAPI or stub. |

**Explicit non-port to client bundle:** everything under `src/routes/api/**` in upstream = **Node server** — use as a **checklist of HTTP behavior** to map to HAM, not as copy-paste.

---

## 4. Upstream same-origin API surface (client fetches) — must map to HAM

*Sample from `grep` on upstream `src/` (incomplete; expand during implementation). All of these are **incompatible** with “browser only `api.ts`” until wrapped.*

| Upstream call pattern (examples) | HAM direction |
|-----------------------------------|---------------|
| `POST/GET /api/send-stream` | **`workspaceChatAdapter` →** `postChatStream` (NDJSON contract). **Never** duplicate TanStack `send-stream` in browser. |
| `/api/sessions`, `/api/history`, session rename/delete | `workspaceSessionAdapter` → HAM chat session APIs. |
| `/api/models`, `/api/model/info`, model switch | Map to HAM `fetchModelsCatalog` / project settings. |
| `/api/hermes-proxy/...` | **Forbidden in browser** — replace with HAM-typed `api.ts` or server route on FastAPI. |
| `/api/gateway/*`, `/api/gateway/sessions` | HAM “gateway” snapshot / hermes hub patterns — not 1:1. |
| `/api/config-get`, `/api/config-patch`, `/api/hermes-config` | `workspaceSettingsAdapter` → preview/apply in HAM. |
| `/api/skills`, memory, knowledge, files, terminal, tasks | Defer, stub, or **FastAPI** work item per [WHOLE_HERMES_WORKSPACE_LIFT_PLAN](WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md). |

A full line-by-line inventory should be a **sheet or appendix** in a later PR: script `ripgrep` on upstream `src` excluding `src/server` to list unique `/api/...` paths.

---

## 5. HAM target structure (recommendation, unchanged from macro plan)

```text
frontend/src/features/hermes-workspace/
  README.md
  WorkspaceApp.tsx        # future: mounted at namespace
  WorkspaceShell.tsx
  styles/workspace.css
  screens/                 # adapted from upstream screen trees (incremental)
  components/
  adapters/
    chatStreamAdapter.ts
    sessionAdapter.ts
    voiceAdapter.ts
    attachmentAdapter.ts
    settingsAdapter.ts
    capabilitiesAdapter.ts
    activityAdapter.ts
    # cloudAgentAdapter.ts, memoryAdapter.ts, swarmAdapter.ts — stubs later
```

**Styles:** single root scoping class to avoid clobbering HAM global theme.

---

## 6. Adapter map (implementation-ready)

| Adapter | Upstream pain points | HAM seam |
|--------|----------------------|----------|
| **Chat** | `use-streaming-message.ts` → `/api/send-stream` | `postChatStream` + event normalization to UI. |
| **Sessions** | `/api/sessions`, history query shapes | `fetchChatSessions` / `fetchChatSession` + `sessionId` in Chat. |
| **Voice** | (if any direct `/api/...` transcribe) | `postChatTranscribe` in `api.ts`. |
| **Attachments** | (composer attachments) | Current Chat attachment inlining; extend only with explicit backend contract. |
| **Settings** | `hermes-config`, `config-patch`, `connection-settings` | `UnifiedSettings` + `postSettingsPreview` / `postSettingsApply`. |
| **Skills / capabilities** | `/api/skills?`, workspace skills screens | HAM hermes-skills + `HamShop` / `HermesSkills` APIs. |
| **Activity / runs** | Mix of dashboard + tasks | HAM `Activity` / `Runs` + `fetchHermesGatewaySnapshot` / `GET /api/runs` — **already** on HAM; reuse in shell. |
| **Cloud Agent** | gateway agents, dispatch | **Later** — use existing HAM mission helpers, no new browser gateway URL. |
| **Memory Heist** | memory browser/write | **Later** — server-mediated Memory Heist only. |
| **SWARM** | (if any in upstream stores) | **Contract** in `SWARM.md`; no upstream SWARM port in browser. |

---

## 7. Namespace decision

| Option | Path | Notes |
|--------|------|--------|
| **Recommended** | `/workspace/*` | Short, product-clear; mount `WorkspaceApp` under HashRouter with same prefix. |
| **Alternate** | `/hermes-lab/*` | Matches [HERMES_WORKSPACE_FEATURE_MATRIX](HERMES_WORKSPACE_FEATURE_MATRIX.md) “lab” language; good if product wants a visible “lab” name. |
| **Decision** | **Use `/workspace/*`** for the **namespaced** lift unless product/legal prefers `hermes-lab` — **document one choice in the first implementation PR**. |

**Feature flag (recommended):** e.g. `VITE_HAM_WORKSPACE_LIFT=1` to show nav entry to `/workspace`; default off until first screens pass smoke.

---

## 8. First three implementation commits (post–Phase 0, post-approval)

1. **Scaffold** — add `features/hermes-workspace/` with `README`, `WorkspaceApp` placeholder, **one** `Route` in `App.tsx` for `/workspace` that renders “Lift in progress” (or shell skeleton only). **No** upstream copy; **no** new deps.  
2. **Shell + static layout** — `WorkspaceShell` layout only (side nav placeholder), still no stream. Styling under `.ham-workspace-root`.  
3. **Chat adapter spike** — one screen: wire send to `postChatStream` only; sessions list can still escape to existing `/chat` if needed.

*Aligns with [WHOLE_HERMES_WORKSPACE_LIFT_PLAN](WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md) and user preference: namespace first, then wire chat, then expand.*

---

## 9. Rollback plan (same as macro doc)

- Remove or disable `Route` for `/workspace`.  
- Env flag off.  
- No database migration; adapters are client-only.  

---

## 10. Build / test / guard checklist (per future PR)

```bash
npm run build --prefix frontend
python -m pytest tests/test_chat_stream.py tests/test_nous_gateway_http_fallback.py
```

Grep in **touched** paths:

`api/send-stream|api/hermes-proxy|HERMES_API_URL|HERMES_DASHBOARD_URL`

Manual: legacy `/chat` and `/command-center` unchanged with flag off.

---

## 11. Red flags (Phase 0 review)

- **Path explosion:** `src/routes/api` in upstream is **large**; treating it as copyable to HAM will fail — **adapters + FastAPI** only.  
- **hermes-proxy in composer** — must never ship as browser call in HAM.  
- **PWA** — do not add service worker to HAM main origin in early commits.  
- **1:1 UX vs 1:1 API** — 1:1 **visual/IA** is the goal; **wiring** is always HAM-shaped.

---

## 12. Next action

- Team **approves** this inventory + [WHOLE_HERMES_WORKSPACE_LIFT_PLAN](WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md).  
- **Implementation** starts with **Commit 1 (scaffold + `/workspace` route + flag)**, with **no** vendored `hermes-workspace` subtree in repo until an explicit “vendor” or “submodule” decision is recorded in `docs/`.
