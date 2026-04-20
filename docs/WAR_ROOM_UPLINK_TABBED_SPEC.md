# HAM War Room — Uplink tabbed surface & resizable split (rewritten spec v1)

**Status:** Implementation in progress per this document.

This refines the existing War Room work in [`frontend/src/pages/Chat.tsx`](frontend/src/pages/Chat.tsx) (single owner for `/chat`). It does **not** redesign product IA, does not restore global **WEB** mode, and does not change Ask / Plan / Agent or Uplink semantics.

---

## 1. Objective

Refine the **War Room** (and split) execution surface so the **right pane** is:

1. **Uplink-specific** (formal mapping: uplink → default tab, tab list, panel component)
2. **Tabbed** (internal subviews; Browser/Preview is a **tab**, not a layout mode)
3. **Resizable** (user-adjustable ratio between transcript and right pane when both are visible)
4. **Backend-ready** (clear view-model / prop contracts; stubs isolated from renderers)
5. **Honest** (explicit stub vs live; no fake IDs/strings presented as runtime truth)

Targeted refinement only — not a broad visual redesign.

---

## 2. Locked semantics (no regression)

- **Ask / Plan / Agent** — directive intent (autonomy), unchanged.
- **Uplink** — execution system / backend family; not a mode; not a replacement for Ask/Plan/Agent.
- **Top workbench modes** — CHAT, SPLIT, PREVIEW, WAR ROOM remain; **no** global WEB mode.
- **`/chat` layout ownership** — remains solely in `Chat.tsx` (AppLayout does not add competing split logic).

---

## 3. When resizable split applies

Apply **draggable divider + persisted ratio (optional `localStorage`)** only when **two columns are visible** (transcript + right execution pane):

- **WAR ROOM** and **SPLIT** — always use resizable two-pane behavior.
- **PREVIEW** — if the product keeps “transcript hidden, full preview column,” define explicitly: either **no resizer** (single column) **or** resizer between two preview subregions — **default in implementation:** keep current PREVIEW behavior (full-width right pane, no left transcript) unless product later changes; **resizer is not required for PREVIEW** if only one column is shown.
- **CHAT** — full-width transcript; no right pane; **no resizer**.

**Clarification:** “Fixed 50/50 is no longer acceptable” applies to **WAR ROOM** and **SPLIT**, not necessarily to PREVIEW’s single-column preview lens.

**Constraints:** min widths (e.g. ~280px / ~320px) for transcript and right pane; usable on narrow viewports (stack or clamp).

---

## 4. Uplink formal contract (code)

Introduce a single source of truth, e.g. `warRoom/uplinkConfig.ts`:

| Uplink ID       | Default tab id   | Tab ids (minimum) |
|-----------------|------------------|-------------------|
| `cloud_agent`   | `tracker`        | `tracker`, `transcript`, `artifacts`, `browser`, `overview` (optional) |
| `factory_ai`    | `swarm`          | `swarm`, `workers`, `queue` or `overview`, `browser` |
| `eliza_os`      | `thought_stream` | `thought_stream`, `context`, `trace`, `browser` |

- `uplink → defaultTab` — on **Uplink change**, optionally reset to that uplink’s default tab (document behavior).
- `uplink → tabs[]` — tab definitions: `{ id, label, icon? }`.
- `uplink → panel` — root component per uplink (thin shell: tab chrome + tab content router).

**Labels in UI:** use **Uplink** everywhere; do not use “Strike Force” or other legacy names.

---

## 5. Tab content rules

- **No hardcoded demo mission IDs, fake PRs, fake workers, or fake uptime** as if live.  
- **Stub data** lives in dedicated modules, e.g. `warRoom/stubs/*` or `warRoom/adapters/*.stub.ts`, exported as **view models** with names like `PlaceholderSwarmStatus`, `EmptyArtifactTrackerState`.
- **Renderers** accept props / view models only; they do not import raw fake rows inline.
- **Cloud Agent** — use real Ham proxies where the UI has a real **`active_cloud_agent_id`** (from launch, Projects, or persisted session):
  - `GET /api/cursor/agents/{id}`
  - `GET /api/cursor/agents/{id}/conversation`
  - `POST /api/cursor/agents/{id}/followup`  
  Wire **Transcript** (and status in **Tracker** when applicable) to these when an id is present.

**Explicit rule (Cloud Agent):** If there is **no** `active_cloud_agent_id`, **every Cloud Agent tab** that depends on mission/agent data must render a **single, intentional UI state**: **“Not connected” / “No active mission”** (clear copy, consistent layout). Do **not** render empty shells, blank panels, or stub transcript rows that could be mistaken for real data. Tabs that do not require a mission (e.g. in-pane **Browser/Preview** URL embed) may still show the embed UI and must not fake agent-backed content.
- **Factory AI / ELIZA_OS** — shell + tabs + stub view models; **no** claim of live execution unless transport exists.

**Browser / Preview tab:** HTTPS embed + external-open; same-origin/mixed-content rules as today; no iframe of cursor.com.

---

## 6. Suggested file layout (implementation-friendly)

Under `frontend/src/components/war-room/` (or equivalent):

- `ResizableWorkbenchSplit.tsx` — divider + min/max widths; optional `localStorage` key for ratio.
- `WarRoomPane.tsx` — right pane shell (tabs + content).
- `WarRoomTabs.tsx` — tab bar driven by config.
- `uplinkConfig.ts` — mapping object + types.
- `CloudAgentPanel.tsx`, `FactoryAIPanel.tsx`, `ElizaOsPanel.tsx` — uplink-specific bodies; delegate to tab subcomponents.
- `BrowserTabPanel.tsx` — shared embed + external link.
- `stubs/*.ts` — placeholder view models only.

Refactor `Chat.tsx` to compose these; avoid another 200-line inline block.

---

## 7. Scope guardrails

- Canvas `#000000`; blur on overlays/drawers only (unchanged).
- Do not remove CHAT / SPLIT / PREVIEW / WAR ROOM.
- Do not change composer order: Ask/Plan/Agent → model → worker → Uplink → tools → input → execute.
- Do not add a new global background grid unless explicitly requested.

---

## 8. Acceptance criteria (binary)

1. **Cloud Agent** War Room default tab = **Artifact & PR Tracker** (Tracker).
2. **Factory AI** default = **Swarm Status Grid** (Swarm).
3. **ELIZA_OS** default = **Thought Stream** (or equivalent ELIZA panel).
4. Right pane has a **visible tab bar** with uplink-specific tabs.
5. **WAR ROOM** and **SPLIT** use a **resizable** split (not fixed 50/50).
6. **Browser/Preview** exists as an **in-pane tab** (not a top-level WEB mode).
7. Stubs are **isolated**; no fake data inlined in core renderers.
8. Cloud Agent proxy routes remain callable from the UI where `agent_id` is known.
9. Demo-ready **without** implying fake live state for Factory/ELIZA.

---

## 9. Deliverables (implementation pass — after spec approval)

1. Implement per this spec in the repo.
2. Summarize **live vs stub** in PR description or comment.
3. List deviations/blockers explicitly.
4. Single commit, e.g. `feat(ham): uplink-specific tabbed war room and resizable split` (adjust if scope differs).

---

## 10. Review notes (prompt red flags / drift — addressed)

| Issue | Resolution in this spec |
|-------|-------------------------|
| Resizable split vs PREVIEW | **§3** — resizer only where two panes are visible; PREVIEW called out. |
| Missing `agent_id` for Cloud Agent API | **§5** — require explicit empty state; wire APIs when `agent_id` exists (add to session/UI state when launch flow exists). |
| Optional tabs scope creep | **§4** — `overview` optional; can omit in v1 if listed. |
| “Formal mapping” | **§4** — `uplinkConfig` + types required. |
| Legacy naming (“Strike Force”) | **§4** — Uplink only. |

**Pause:** Superseded by implementation; spec remains the contract for behavior.
