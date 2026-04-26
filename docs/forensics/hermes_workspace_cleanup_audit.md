# Hermes Workspace — Legacy Forensic Cleanup Audit

**Audit date:** 2026-04-26  
**Scope:** Evidence-based inventory only. **No deletions, moves, edits, or commits** were performed as part of this document.  
**Product assumption:** Hermes Workspace (`/workspace/*`) is primary; War Room / legacy workbench surfaces are **candidates** for removal after human sign-off.

**Cleanup Batch 1 (post-audit):** Mock `/extensions` route, `Extensions.tsx`, and `MOCK_EXTENSIONS` were **removed** from the repo; use `/shop` and Capability Directory for real capability discovery.

---

## 1. Executive summary

- **Primary chat path:** `/chat` → redirect → `/workspace/chat` (`App.tsx` `ChatEntryRoute`). Nav primary “Chat” uses `primaryChatPath()` → workspace chat (`NavRail.tsx`).
- **Legacy full workbench:** `/legacy-chat` still mounts `frontend/src/pages/Chat.tsx`, which owns the **War Room** stack (`WarRoomPane`, `CloudAgentPanel`, `BrowserTabPanel`, resizable split, workbench modes). This is **reachable only by direct URL** (not in `NavRail` primary or diagnostics lists).
- **Browser / Browser Operator (frontend):** All runtime calls to `/api/browser/*` and `/api/browser-operator/*` from the frontend are confined to **`BrowserTabPanel.tsx`** and helpers in **`api.ts`**. **`HermesHub.tsx`** only documents `/api/browser/policy` textually and uses `fetchBrowserRuntimePolicy()` — it does not drive Playwright sessions. **Hermes Workspace screens** do not import `BrowserTabPanel` or browser session helpers (grep verified under `frontend/src/features/hermes-workspace`).
- **Extensions:** *(removed Batch 1.)* Previously a mock page at `/extensions` with `MOCK_EXTENSIONS`; discovery is **`/shop`** / Capability Directory / My Library.
- **Backend:** `/api/browser` and `/api/browser-operator` are **fully wired** in `src/api/server.py` with dedicated tests (`test_browser_runtime_api.py`, `test_browser_operator_api.py`, `test_browser_proposal_store.py`, `test_browser_runtime_sessions.py`). Removing them is **not** a frontend-only cleanup; it requires API + persistence + test + doc alignment.
- **Control panel:** `ControlPanelOverlay` is mounted for immersive routes (`/chat`, `/workspace/*`, `/legacy-chat`) in `AppLayout.tsx`. It is a **large UI shell** (settings-style overlay); overlap with Workspace settings routes needs **human decision** before removal.
- **Risks:** `VISION.md`, `README.md`, `src/api/chat.py` system prompt, `managedCloudAgent.ts`, UI actions, and workbench intent tests **still describe War Room / browser workbench** behavior tied to legacy chat. Removing War Room without updating these will **break narrative, operator hints, and tests**.

---

## 2. Current app surface map (frontend routes)

**Source of truth inspected:** `frontend/src/App.tsx`, `frontend/src/components/layout/NavRail.tsx`, `frontend/src/features/hermes-workspace/WorkspaceApp.tsx`.

### 2.1 Active routes (registered)

| Route | Component | Nav exposure |
|-------|-----------|--------------|
| `/` | `Landing` (web) / redirect to chat (desktop) | Logo home |
| `/workspace/*` | `WorkspaceApp` | **Primary “Chat”** → `/workspace/chat`; sub-routes: chat, files, terminal, settings, jobs, tasks, conductor, operations, memory, skills, profiles |
| `/chat` | `Navigate` → `/workspace/chat` | Same as workspace chat (redirect) |
| `/legacy-chat` | `Chat` (legacy workbench) | **Hidden** (no nav link) |
| `/command-center` | `CommandCenter` | **Primary nav** |
| `/activity` | `Activity` | **Primary nav** |
| `/shop` | `HamShop` | **Primary nav** (“Capabilities”) |
| `/agents` | `AgentBuilder` | **Primary nav** |
| `/runs`, `/runs/:runId` | Runs | Diagnostics menu |
| `/control-plane` | `ControlPlaneRuns` | Diagnostics menu |
| `/storage` | `Storage` | Standard shell (no primary icon — still routed) |
| `/settings` | `Settings` | Settings button (rail) |
| `/logs`, `/analytics` | Logs, Analytics | Diagnostics menu |
| `/hermes` | `HermesHub` | Diagnostics (“Hermes details”) |
| `/skills` | `HermesSkills` | Diagnostics + redirect from `/hermes-skills` |
| `/hermes-skills` | `Navigate` → `/skills` | Legacy URL |
| `/droids` | `Navigate` → `/command-center` | Legacy URL |
| `/profiles` | `Navigate` → `/agents` | Legacy URL |
| `/overview` | `Navigate` → `/activity` | Legacy URL |

### 2.2 Hermes Workspace nested routes

From `WorkspaceApp.tsx`: `chat`, `files`, `terminal`, `settings` (+ `settings/mcp`), `jobs`, `tasks`, `conductor`, `operations`, `memory`, `skills`, `profiles`; index → `WorkspaceHome`.

### 2.3 Classification (direction fit)

| Area | Fit with Hermes Workspace–first | Notes |
|------|----------------------------------|-------|
| `/workspace/*` | **keep** | Product core |
| `/legacy-chat` + `Chat.tsx` + `components/war-room/*` | **remove** (after migration) | War Room / browser / CloudAgentPanel; only consumer is legacy route |
| ~~`/extensions` + `MOCK_EXTENSIONS`~~ | **removed** (Batch 1) | Mock surface deleted |
| `/shop`, capability library/directory | **keep** (per product) | Align copy with “discovery” not execution |
| `/skills` vs `/shop` | **human decision** | Both exist; diagnostics links Skills |
| `/hermes` | **keep** (diagnostics) | Copy references browser policy / War Room in places — **stale terminology** |
| `/command-center` | **keep** (per product) | API-side snapshot; not Workspace shell |
| `ControlPanelOverlay` | **human decision** | Global overlay on workspace + legacy chat |

---

## 3. Frontend dependency graph (high-value files)

**Legend:** Rec = recommendation for * eventual* cleanup (not executed here).

| File / folder | Imported by | Route / nav reachable? | Direction fit | Rec | Risk |
|---------------|-------------|--------------------------|---------------|-----|------|
| `pages/Chat.tsx` | `App.tsx` (`/legacy-chat` only) | Hidden URL | Legacy workbench | **remove** (after cutting route) | Large; cloud agent, deploy, missions |
| `components/war-room/*` (15 files) | `Chat.tsx` primarily | Via legacy only | War Room execution chrome | **remove** with `Chat.tsx` | `CapabilityBundleDetail` links `/legacy-chat` |
| `BrowserTabPanel.tsx` | `CloudAgentPanel`, `FactoryAIPanel`, `ElizaOsPanel` | Legacy | Browser + operator UI | **remove** if War Room removed | Only FE consumer of `/api/browser*` |
| `BrowserProposalTray.tsx`, `BrowserProposeForm.tsx` | `BrowserTabPanel` | Legacy | Browser operator | **remove** with panel | None beyond panel |
| `components/chat/*` used by `Chat.tsx` | `Chat.tsx` | Legacy | Mixed | **migrate first** / trim | Some may be shared — prove per file |
| `WorkspaceApp.tsx` + `WorkspaceShell.tsx` + screens | `App.tsx` | Primary | Core | **keep** | — |
| ~~`pages/Extensions.tsx`~~ | — | — | — | **removed** (Batch 1) | — |
| ~~`MOCK_EXTENSIONS` in `mocks.ts`~~ | — | — | — | **removed** (Batch 1) | — |
| `pages/HamShop.tsx` | `App.tsx` | Primary | Discovery | **keep** | — |
| `pages/HermesSkills.tsx` | `App.tsx` | Diagnostics | Catalog | **keep** / align with Shop | — |
| `pages/HermesHub.tsx` | `App.tsx` | Diagnostics | Diagnostics | **keep** | Stale “War Room” copy |
| `pages/CommandCenter.tsx` | `App.tsx` | Primary | Broker snapshot | **keep** | — |
| `components/workspace/ControlPanelOverlay.tsx` | `AppLayout.tsx` | Workspace + legacy immersive | Unclear | **human decision** | UX coupling |
| `lib/ham/api.ts` (browser section) | `BrowserTabPanel`, `HermesHub` (policy only) | — | Split | **trim** after FE removal | Many other APIs share file |

**Reachability note:** Nothing in `frontend/src/features/hermes-workspace` imports `war-room` or `BrowserTabPanel` (grep 2026-04-26).

---

## 4. Backend API map (routers in `src/api/server.py`)

**Inspect method:** `server.py` includes + per-router `prefix` grep.

### 4.1 Route families

| Prefix / family | Backend module | Primary FE consumers (evidence) | Tests | Direction fit | Rec |
|-----------------|----------------|----------------------------------|-------|---------------|-----|
| `/api/browser` | `browser_runtime.py` | `BrowserTabPanel` only (FE) | `test_browser_runtime_api.py`, `test_browser_runtime_sessions.py` | Legacy War Room browser | **human decision** — remove only if product drops in-browser Playwright |
| `/api/browser-operator` | `browser_operator.py` | `BrowserTabPanel` + `api.ts` | `test_browser_operator_api.py`, `test_browser_proposal_store.py` | Tied to browser surface | Same as browser |
| `/api/workspace/*` | `workspace_*.py`, `workspace_health.py` | Workspace screens | Many `test_workspace_*.py` | Core | **keep** |
| `/api/chat`, `/api/chat/stream` | `chat.py` | Workspace chat, legacy `Chat.tsx` | `test_chat_*.py` | Core + legacy | **keep**; trim legacy-only branches later |
| `/api/hermes-gateway/*` | `hermes_gateway.py` | Command center, chat adapters | `test_hermes_gateway_*.py` | Core | **keep** |
| `/api/hermes-hub` | `hermes_hub.py` | `HermesHub.tsx` | `test_hermes_hub.py` | Diagnostics | **keep** |
| `/api/hermes-runtime/*` | `hermes_runtime_inventory.py` | Inventory UIs | `test_hermes_runtime_inventory.py` | Discovery/diagnostics | **keep** |
| `/api/hermes-skills/*` | `hermes_skills.py` | Skills page, shop, settings | `test_hermes_skills_*.py` | Discovery | **keep** |
| `/api/capability-directory` | `capability_directory.py` | Shop, directory panels | `test_capability_directory.py` | Discovery | **keep** |
| `/api/capability-library` | `capability_library.py` | Shop / library | `test_capability_library.py` | Discovery | **keep** |
| `/api/cursor/*` | `cursor_*.py` | Legacy chat, managed missions, settings | Many tests | Mixed | **migrate first** — large surface |
| `/api/control-plane-runs` | `control_plane_runs.py` | Control plane UI | `test_control_plane_runs_api.py` | Ops/diagnostics | **keep** |
| `/api/models` | `models_catalog.py` | Workspace + settings | `test_models_catalog.py` | Core | **keep** |
| `/api/projects/*`, settings writes | `project_settings.py` | Agent builder, workspace | `test_project_settings_writes.py` | Core | **keep** |

### 4.2 Browser API vs Workspace

**Finding:** No `frontend/src/features/hermes-workspace` usage of `createBrowserSession`, `captureBrowserScreenshot`, or `browser-operator` paths. **Hermes Workspace chat** is documented as `/api/chat/stream` only in `WorkspaceChatScreen.tsx` header comment.

---

## 5. Tests audit

| Test file | Target | Keep / remove / update | Depends on |
|-----------|--------|------------------------|------------|
| `test_browser_runtime_api.py` | `/api/browser` | **remove** only if API removed; else **keep** | Backend browser |
| `test_browser_runtime_sessions.py` | `BrowserSessionManager` | Same | Backend browser |
| `test_browser_operator_api.py` | `/api/browser-operator` | Same | Operator + browser |
| `test_browser_proposal_store.py` | `BrowserProposalStore` | Same | Operator persistence |
| `test_workspace_*.py` | Workspace APIs | **keep** | Core |
| `test_workbench_view_intent.py` | `workbench_view_intent.py` | **update** if legacy workbench removed | Chat operator / legacy UI actions |
| `test_ui_actions.py` | `ui_actions.py` war_room / browser modes | **update** if modes removed | Legacy chat |
| `test_chat_operator.py`, `test_chat_stream.py`, … | Chat | **keep**; **review** for legacy-only assertions | Chat route split |
| `test_capability_directory.py` | Directory bundles | **keep**; mentions `playwright_browser_service` | Product copy |
| `test_hermes_hub.py` | Hermes hub API | **keep** | Diagnostics |

---

## 6. Docs audit (sampled + grep-driven)

| Doc | Stale refs | Rec | Notes |
|-----|------------|-----|-------|
| `docs/WAR_ROOM_UPLINK_TABBED_SPEC.md` | Entire doc War Room | **stale — remove or rewrite** | Describes `/chat` as owner; product now redirects `/chat` |
| `docs/DEPLOY_CLOUD_RUN.md` | Chat → Browser / War Room | **rewrite** | Ops still need Playwright if browser API kept |
| `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` | War Room / CloudAgentPanel | **rewrite** | May still be true for **legacy** until removed |
| `docs/HAM_SHELL_PRESERVING_REBUILD_PLAN.md` | war-room migration | **stale / rewrite** | Plan predates “Workspace only” |
| `docs/capabilities/computer_control_pack_v1.md` | War Room, Browser Operator Phase 2 | **rewrite** | Future desktop/local; decouple from War Room browser |
| `VISION.md` | War Room / Chat table row | **rewrite** after cleanup | Canonical architecture |
| `README.md` | In-app browser Chat → War Room | **rewrite** if surface removed | |
| `AGENTS.md` | (not fully scanned) | **review** | Likely mentions browser pane |

**Classification rule:** Anything that states **primary** chat is `/chat` or **requires** War Room for product should be treated **stale** relative to Hermes Workspace–first direction.

---

## 7. Terminology audit (representative)

| Term | Example locations | Problem | Rec |
|------|-------------------|---------|-----|
| War Room | `Chat.tsx`, `docs/*`, `VISION.md`, `managedCloudAgent.ts`, `HermesHub.tsx` | Implies legacy split/workbench is current | Replace with “legacy workbench” or remove refs |
| Browser Operator | `war-room/*`, `api.ts`, `browser_operator.py`, `computer_control_pack_v1.md` | Coupled to War Room UI in FE | Repoint spec to **future** surface or drop |
| Computer Control | `docs/capabilities/*`, `capability_directory_v1.json` | Correct as **future/local**; doc ties to `/api/browser` | Clarify **not** War Room |
| goHAM | `computer_control_pack_v1.md`, `capability_directory_v1.json`, `readiness.py` | Future phrase; fine if labeled future | **keep** with clear “not shipped” |
| ~~MOCK_EXTENSIONS~~ | *(removed)* | Mock as product | **Removed** Batch 1 |
| Hermes Workspace | `WorkspaceApp.tsx`, flags | Primary — good | Standardize capitalization in docs |
| legacy-chat | `App.tsx`, `AppLayout.tsx` | Explicit escape hatch | Remove when workbench deleted |
| archive | `ControlPanelOverlay` imports `Archive` icon | Cosmetic | N/A |

---

## 8. Removal candidates (three lists)

### A. Safe removal candidates (frontend-only, after route cut — **verify again before deleting**)

**Condition:** Product accepts dropping `/legacy-chat` and in-app Playwright browser entirely.

- `frontend/src/pages/Chat.tsx` — only routed from `/legacy-chat`.
- `frontend/src/components/war-room/**` — only imported from `Chat.tsx` (re-verify `CapabilityBundleDetail` link to `/legacy-chat`).
- ~~`frontend/src/pages/Extensions.tsx` + `MOCK_EXTENSIONS`~~ — **done (Batch 1).**
- **Partial:** Browser-only exports in `frontend/src/lib/ham/api.ts` — **only after** no remaining imports.

**Not automatically safe:** Shared `components/chat/*` — must prove each file’s importers.

### B. Remove after migration

- **Cloud Agent / managed mission UX** if still desired: extract from `Chat.tsx` into Workspace or Command Center **before** deleting the page.
- **`src/api/chat.py` workbench instructions** — migrate prompt to Workspace-only or remove `set_workbench_view` modes.
- **`src/ham/ui_actions.py` + tests** — migrate or drop `war_room` / `browser` modes.
- **Backend `/api/browser` + `/api/browser-operator` + `src/persistence/browser_proposal.py` + `src/ham/browser_runtime/*` + `src/ham/browser_operator/*`** — **migration**: none if product keeps Playwright for a **new** Workspace surface; else full API removal batch.

### C. Human decision

- **Keep Playwright API, drop War Room only:** Retarget Browser Operator UI to Workspace (new issue) vs delete operator entirely.
- **`ControlPanelOverlay`:** Still shown on `/workspace/*`; remove vs replace with native workspace panels.
- **`/skills` vs `/shop`:** Single discovery IA or both.
- **`VISION.md` / public README** positioning.

---

## 9. Proposed cleanup batches (for future execution)

Each batch: small commit; run validation; **no** `git add .`.

### Batch 1 — Mock Extensions (**done**)
- Removed: `Extensions.tsx`, `/extensions` route in `App.tsx`, `MOCK_EXTENSIONS` from `mocks.ts`, `/extensions` from `ui_actions.py` allowlist; docs updated.
- Tests: FE `npm run lint && npm run build`.
- Risk: Low.

### Batch 2 — Legacy route + War Room frontend
- Remove: `/legacy-chat`, `Chat.tsx`, `components/war-room/**`, shared chat components only if unused.
- Update: `AppLayout.tsx`, `Header.tsx`, `CapabilityBundleDetail.tsx`, `api.ts` imports.
- Tests: FE build; grep for broken imports; Python tests if chat operator references workbench modes.

### Batch 3 — Backend browser (optional product gate)
- Remove: `browser_runtime_router`, `browser_operator_router`, persistence store, ham modules.
- Tests: drop `test_browser_*.py`; run full `pytest`.
- Risk: High — Cloud Run / README / HermesHub docs assume Playwright.

### Batch 4 — Docs alignment
- Rewrite/remove War Room specs; update `VISION.md`, `README.md`, `DEPLOY_CLOUD_RUN.md`.

### Batch 5 — Operator / workbench strings in code
- `managedCloudAgent.ts`, `chat.py` prompts, `workbench_view_intent.py`.

---

## 10. Validation plan (per batch)

| Batch | Commands |
|-------|----------|
| FE only | `cd frontend && npm run lint && npm run build` |
| Backend | `.venv/bin/python -m pytest tests/test_<affected>.py -v` then full `pytest` |
| API smoke | Manual: `/api/status`, workspace health, `/api/chat/stream` smoke |
| CLI | `./scripts/ham doctor` or `python -m src.ham_cli` per `AGENTS.md` |

---

## 11. Risks

- **Undiscovered dynamic imports** or string-based routes (search `navigate(\"` for `legacy-chat`).
- **Desktop shell** may assume old paths — inspect `desktop/` and `desktopConfig` (not fully audited in this pass).
- **External docs / bookmarks** to `/legacy-chat`. *( `/extensions` route removed.)*
- **Cursor / managed cloud** flows may still depend on legacy composer behaviors in `Chat.tsx`.

---

## 12. Files and artifacts inspected (exact)

**Frontend:** `App.tsx`, `NavRail.tsx`, `AppLayout.tsx` (partial), `Header.tsx` (grep), `WorkspaceApp.tsx`, `WorkspaceChatScreen.tsx` (header), ~~`Extensions.tsx`~~ (removed Batch 1), `CommandCenter.tsx` (header), `Chat.tsx` (header + imports), `HermesHub.tsx` (grep), `ControlPanelOverlay.tsx` (partial), all files under `frontend/src/components/war-room/`, grep under `frontend/src/features/hermes-workspace`, `CapabilityBundleDetail.tsx` (grep), `api.ts` (browser sections + grep consumers).

**Backend:** `src/api/server.py`, grep `prefix=` across `src/api/*.py`, `src/api/chat.py` (workbench comment grep), `src/api/browser_runtime.py` / `browser_operator.py` (referenced via tests and grep).

**Tests:** Listed `tests/*.py`; detailed grep for `browser`, `war_room`, `legacy`.

**Docs / data:** Grep in `docs/` for War Room / Browser Operator / Computer Control; `src/ham/data/capability_directory_v1.json` (referenced), `VISION.md` (grep), `README.md` (grep).

**Other:** `src/ham/workbench_view_intent.py`, `src/ham/ui_actions.py` (references), `frontend/src/lib/ham/managedCloudAgent.ts` (grep).

---

## 13. Next step (human)

1. Decide **product fate** of: in-app Playwright (`/api/browser`), Browser Operator, Cloud Agent panels currently in legacy `Chat.tsx`.  
2. If **Workspace-only**: approve Batch 2+4 in principle; schedule backend batch only if API truly unused.  
3. Review further batches (War Room, browser API, etc.) before execution; Batch 1 landed in-repo.

---

*End of audit — no repository mutations performed.*
