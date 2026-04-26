# Whole Hermes Workspace lift into HAM (strategy plan)

**Status:** planning document. **Not** an instruction to start bulk copy/paste in code until the team approves this plan and a Phase 0 inventory exists.

**Phase 0 inventory (pinned commit, API map, namespace):** [PHASE0_HERMES_WORKSPACE_INVENTORY.md](PHASE0_HERMES_WORKSPACE_INVENTORY.md)

**Strategic correction (why this supersedes page-by-page “old HAM skinning” after `c3b0578`):**  
Incremental restyling of legacy route components converges too slowly toward the *product* goal: **a single Hermes Workspace–class operator experience** driven by HAM’s runtime. Commits through `c3b0578` (shell, nav/header, activity/runs) remain useful foundations and **are not reverted**; **new** work should pivot to a **wholesale UI lift + adapter layer**, not “Commit 4 Command Center cosmetics.”

---

## 1. Recommended lift strategy (options A / B / C)

| Option | Summary | Speed | Risk | Rollback | Duplication |
|--------|---------|------|------|----------|------------|
| **A — Workspace app inside HAM providers** | Vendored `WorkspaceApp` tree under e.g. `frontend/src/features/hermes-workspace/`, mounted from `App.tsx`, uses existing Clerk/Theme/Agent/Workspace providers. | High when promoted to primary | Medium–high: route collisions, CSS bleed | Revert feature flag / route mount | Low if one shell wins |
| **B — Replace app shell** | `AppLayout` becomes thin wrapper; primary chrome is `WorkspaceShell` for (almost) all routes. | High | **Highest** if done as big-bang | Hard without flags | Can spike during migration |
| **C — Namespace first, then promote** | Mount lifted UI under e.g. `/workspace/*` or historic `/hermes-lab/*` (see [HERMES_WORKSPACE_FEATURE_MATRIX.md](HERMES_WORKSPACE_FEATURE_MATRIX.md)), verify adapters, then **gradually** swap primary routes. | Slower to “full” UX on `/chat` | **Lowest** | **Best**: disable route, keep old pages | **Temporary** (two UIs) |

**Recommendation:** **Option C first, then converge on Option A.**

- **C** gives a safe place to port upstream layout/navigation and prove **stream/session/settings adapters** without breaking production routes on day one. Aligns with [`.cursor/plans/hermes_workspace_integration.md`](.cursor/plans/hermes_workspace_integration.md) (namespace, no blind `/api` shim).
- **A** is the end state: one React tree, `WorkspaceShell` as the product frame, HAM `api.ts` as the only browser transport seam.
- **B** is an execution style for the *same* code (aggressive cutover); use only with **feature flags** and a rollback branch.

**Relationship to work already in HAM:** `frontend/src/features/operator-workspace/` is an early **A-style** island for `/chat`. The lift should **absorb or replace** that module over time so there is not two competing “Workspace” implementations long term.

---

## 2. Upstream “source of truth” — what we can and cannot name exactly

**Blocker (explicit):** This repository does **not** include a vendored `outsourc-e/hermes-workspace` tree. The plan **cannot** honestly list file-level paths like `hermes-workspace/src/routes/...` *from this clone* without **Phase 0: upstream checkout**.

**Phase 0 (required first implementation slice, doc-only or repo hygiene):**

1. Pin a **version/commit** of upstream (or internal fork).
2. Either:
   - **Git submodule** at e.g. `third_party/hermes-workspace/` (read-only reference), or  
   - A **separate worktree/clone** + doc link in this repo, or  
   - **Subtree** if license and maintenance are acceptable.
3. Produce an **API surface inventory**: every `fetch('/api/...')` (or client helper) in upstream, mapped to HAM FastAPI or **explicitly stubbed** for later.

**Illustrative upstream areas** (to be verified against actual tree at Phase 0) — from prior integration review:

- App shell / root layout, global styles, PWA boot (treat PWA as **out of scope** for HAM main origin per existing guardrails).
- Chat route(s) and stream caller(s).
- Session sidebar / list / key model.
- Settings surface(s) and form wiring.
- Skills / capabilities UIs and any “memory” or “tools” panes.
- **Do not** treat Node/TanStack server routes as portable; re-home behavior behind **adapters** calling [`frontend/src/lib/ham/api.ts`](frontend/src/lib/ham/api.ts).

**License / attribution:** Any copied files require compliance with upstream license; prefer **inspired reimplementation** in HAM components over bulk paste when possible.

---

## 3. Target structure in HAM (concrete but adjustable)

Proposed feature root:

```text
frontend/src/features/hermes-workspace/
  README.md                 # how adapters map to HAM, what is not ported
  WorkspaceApp.tsx          # top-level: routes + shell, under HAM providers
  WorkspaceShell.tsx        # nav, sidebar, mobile drawer, content outlet
  styles/
    workspace.css           # scope under .ham-workspace-root to reduce global collision
  screens/                  # route-level compositions (or mirror upstream IA)
  components/               # lifted or rewritten presentational components
  adapters/
    index.ts
    chatStreamAdapter.ts
    sessionAdapter.ts
    voiceAdapter.ts
    attachmentAdapter.ts
    settingsAdapter.ts
    capabilitiesAdapter.ts
    cloudAgentAdapter.ts    # stub / later
    memoryAdapter.ts        # stub / later
    swarmAdapter.ts         # contract-only / later
```

Mount point options:

- **During C:** `App.tsx` adds `<Route path="/workspace/*" element={<WorkspaceApp />} />` (path name TBD by product).
- **After promote:** `AppLayout` (non-chat) and `/chat` both delegate to the same `WorkspaceShell` or merge operator-workspace into this tree.

**Style isolation:** a single **root class** (e.g. `.ham-workspace-root`) and CSS layers or CSS modules; avoid unscoped edits to [`frontend/src/index.css`](../src/index.css) that affect legacy pages still mounted during transition.

---

## 4. Adapter layer (seams, not a framework)

All browser I/O goes through HAM’s existing client. **No** new transport in the browser to upstream Hermes URLs or keys.

| Adapter | Responsibility | HAM touchpoints (illustrative) | Notes |
|---------|----------------|--------------------------------|--------|
| `workspaceChatAdapter` | Map UI send/stop to `postChatStream` / `postChat`; map NDJSON events to whatever the lifted message list expects. | [`api.ts`](../frontend/src/lib/ham/api.ts) | Upstream `send-stream` **never** in browser. |
| `workspaceSessionAdapter` | List/switch/rename session if/when product supports; map to HAM `fetchChatSessions` / `fetchChatSession` patterns. | Existing chat session API via `api.ts` | Session **key** model may differ; adapter owns mapping. |
| `workspaceVoiceAdapter` | Wire mic UI to `postChatTranscribe` or local preview-only until server contract frozen. | `api.ts` + current Chat voice path | Reuse, don’t fork secrets. |
| `workspaceAttachmentAdapter` | Local preview; send path unchanged from today’s inlining/attachment story unless backend adds a contract. | Chat composer behavior | “Deferred” is OK. |
| `workspaceSettingsAdapter` | Map Hermes settings IA to `UnifiedSettings` / `postSettingsPreview` / `postSettingsApply`. | Settings flows | **Visual** port may precede full IA. |
| `workspaceCapabilitiesAdapter` | Map skills/capability UI to HAM hermes-skills + capability library endpoints. | `api.ts` + capability routes | Distinguish HAM library vs Hermes runtime skills. |
| `workspaceCloudAgentAdapter` | **Later** — mission UI; preserve existing Cloud Agent API usage. | Managed mission surfaces | Defer first-class port. |
| `workspaceMemoryAdapter` | **Later** — read-only or preview via Memory Heist seams; no upstream memory URLs. | Server-mediated only | [HAM_SHELL_PRESERVING_REBUILD_PLAN](HAM_SHELL_PRESERVING_REBUILD_PLAN.md) |
| `workspaceSwarmAdapter` | **Later** — treat `SWARM.md` as contract, not a UI bundle. | — | — |

**Rule:** one thin file per concern is enough; avoid abstract factories unless complexity demands.

---

## 5. What HAM runtime must be preserved (non-negotiable)

- **Browser contract:** [`frontend/src/lib/ham/api.ts`](../frontend/src/lib/ham/api.ts) (no new browser→gateway shortcuts).
- **Chat:** `postChatStream`, gateway semantics in [HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md).
- **Auth:** Clerk session behavior, deployment restricted banner, desktop `HashRouter` if applicable.
- **Backend:** `backend/src/api/*`, `backend/src/integrations/*`, deploy scripts, secrets on API only.
- **Cloud Agent / SWARM / Memory Heist:** **contracts preserved**; full Workspace-style **tooling UI** is optional and later.

**Forbidden in the lift (same as prior guardrails):** browser `HERMES_API_URL` / `HERMES_DASHBOARD_URL`, ad hoc `api/send-stream` in client, `api/hermes-proxy` in client, PWA/SW for main app without separate decision, terminal/xterm/PTY/files in browser until policy approval.

---

## 6. What old HAM UI may be superseded (when promoted)

- Legacy `AppLayout` chrome (partially already aligned), `NavRail`/`Header` as **separate** design language — replaced by `WorkspaceShell` for primary routes.
- Per-page `CommandCenter`, `Activity`, `Runs`, `Settings`, `HamShop`, `HermesSkills`, `AgentBuilder` **presentations** — replaced by **Workspace screens** that call the same APIs via adapters, **or** left as **fallback** behind a flag during transition.
- `operator-workspace` — merged into the lifted app or removed after parity.

**Preserve:** business behavior, API contracts, and data semantics—not pixel-perfect legacy components.

---

## 7. Route mapping (current HAM → lift outcome)

*Default under Option C: existing routes **unchanged** until feature flag; new Workspace lives under `prefix`. Under promotion (Option A), each route **renders** a Workspace **screen** component.*

| Route | Suggested lift handling |
|-------|-------------------------|
| `/chat` | **First-class Workspace chat screen**; merge existing operator-workspace + stream adapter. |
| `/command-center` | Workspace “operator / system health” view OR redirect into Workspace dashboard tab until a single IA is decided. |
| `/activity` | Workspace activity/feed screen; same `fetchHermesGatewaySnapshot` data via adapter. |
| `/shop` | Capabilities / library surface. |
| `/skills` | Hermes skills catalog surface (separate from `/shop` until IA merged later). |
| `/agents` | Agent profiles (HAM semantics preserved). |
| `/runs` / `/runs/:id` | Run list/detail screens; no transport change. |
| `/settings` | Workspace settings pattern; `UnifiedSettings` data via `workspaceSettingsAdapter`. |
| `/hermes`, `/control-plane`, `/logs`, `/analytics` | **Diagnostics** — secondary nav in Workspace; may stay “HAM” pages behind adapter until lift. |
| `/extensions`, `/storage` | **Defer** or embed as Workspace panels. |

**Conflicts with [HERMES_WORKSPACE_FEATURE_MATRIX.md](HERMES_WORKSPACE_FEATURE_MATRIX.md):** the matrix allows experimental UI under e.g. `/hermes-lab/*`. A **decision** is required: either update that doc to the new `prefix` (e.g. `/workspace/*`) or keep `/hermes-lab/*` for **non-production** and use `/workspace/*` for production validation.

---

## 8. Feature classification

| Area | Class |
|------|--------|
| Chat, composer, sessions (basic), shell nav | **Lift with HAM adapter now** (highest value) |
| Voice, attachments | **Lift UI now**; keep current HAM send/transcribe contracts |
| Settings, capabilities/skills, activity, runs | **Lift with adapter**; may be phased by screen |
| Cloud Agent, Memory Heist, SWARM tooling | **Defer** visible first-class; preserve APIs |
| Terminal, files, process | **Defer / unsafe** until separate runtime decision |
| PWA, mobile as separate app shell | **Defer** HAM main SW; **allow** responsive Workspace CSS |

---

## 9. First three implementation commits (after plan approval)

**These are HAM repo commits, not unbounded work in one drop.**

1. **Phase 0 + scaffold:** Document upstream version pin; add empty `features/hermes-workspace/` with `README`, `WorkspaceApp` stub, and **one** `Route` under agreed prefix; **no** user-facing design change. Add inventory checklist (list of upstream API calls from checkout).
2. **Shell + chat adapter spike:** `WorkspaceShell` + port **one** screen (e.g. chat) wired **only** through `workspaceChatAdapter` to existing `postChatStream`; other links in Workspace nav point to **existing** HAM routes (escape hatch) or placeholders.
3. **Session + settings read path:** `workspaceSessionAdapter` for list/selection where API exists; `workspaceSettingsAdapter` read-only or preview-only for one panel.

*Parallel governance:* no more **legacy-only** full-page reskins unless unblocking the lift; small bugfixes OK.

---

## 10. Rollback strategy

- **Feature flag** (e.g. env or runtime config): `VITE_HAM_WORKSPACE_LIFT=0` hides `WorkspaceApp` route; primary routes 100% legacy.
- **Prefix isolation:** if `/workspace/*` is bad in prod, remove route; main app unchanged.
- **Git:** one branch for lift, merge to `main` in slices; `main` always releasable with flag off.
- **Data / API:** no migration required for pure UI port if adapters only call existing endpoints.

---

## 11. Build, test, smoke gates

- `npm run build --prefix frontend`
- `python -m pytest` (at minimum existing chat stream / gateway tests)
- Guard: no `api/send-stream` / `api/hermes-proxy` / `HERMES_API_URL` / `HERMES_DASHBOARD_URL` in new workspace feature paths
- **Manual:** prefix route loads; legacy `/chat` still works with flag off; with flag on, chat send still hits HAM only

---

## 12. “What to say back to Cursor / team” (short)

Stop treating **Command Center** or **Settings** as the next *cosmetic* horizon. The next planning unit is the **Whole Hermes Workspace lift**: vendor or reference upstream (Phase 0), add **namespace + adapters**, then promote **one shell + chat** to primary. Preserve **all** HAM API/auth/backend seams; do not copy TanStack/Node `send-stream` to the browser. **Option C (namespace) then Option A (single app)** is the recommended path for speed/risk balance.

---

## Revision notes (this doc vs. older matrix)

- [HERMES_WORKSPACE_FEATURE_MATRIX.md](HERMES_WORKSPACE_FEATURE_MATRIX.md) is still valid for **feature-by-feature** phasing; this doc is the **macro** product strategy.
- If “whole Workspace” and “/hermes-lab only” conflict, **update the matrix in a follow-up commit** so there is a single source of truth for routes.
