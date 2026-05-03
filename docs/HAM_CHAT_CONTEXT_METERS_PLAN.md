# Ham chat — three context meters (plan for review)

**Status:** proposal — no implementation obligation from this doc.

**Goal:** Surface **three** at-a-glance rings beside workspace chat (Cursor-style), with **green → amber → red**, **short** hover tooltips, and **one actionable nudge** when usage is high. **Layout:** rings on the **composer bottom-right** (before mic/send); **unify** bottom-toolbar control sizes for a single visual rhythm.

---

## 0. Review notes (red flags addressed)

| Issue | Resolution in this revision |
|-------|------------------------------|
| **Draft “this turn”** | A **GET** with only `session_id` cannot see the user’s **unsent** composer text. Either **POST** a preview body, **client-side char heuristic** for drafts (labeled estimate), or **v1 = post-send only** (ring updates after stream completes). |
| **Model context limit** | **200K is not universal.** Meter must use **selected `model_id`** + catalog / provider **max context** (or a conservative default), not a hardcoded constant. |
| **`/api/chat/capabilities`** | It is **GET**, not POST — any “capabilities” integration must match the existing route. |
| **Workspace vs cloud** | **Workspace** ring must declare **`source`: `local` \| `cloud` \| `unavailable`** and use the **same routing** as Context & memory (local snapshot when connected + root configured; else cloud `context-engine` / project chain). Avoid implying a laptop path when the payload is `/app`. |
| **Workspace cost** | Full `ProjectContext.discover` on every poll is risky. Prefer **reusing the same snapshot path** as the settings panel (cache, TTL, or shared backend helper) rather than ad-hoc rediscovery per request. |
| **Clerk** | Match existing chat/session routes: when `HAM_CLERK_REQUIRE_AUTH` / email enforcement is **off**, meters remain callable like today’s chat; when **on**, require the same **Bearer** pattern as `GET /api/chat/sessions`. |
| **Feature flag** | Server-side **`HAM_CONTEXT_METERS`** is fine; if the UI needs a switch without redeploy, expose **`context_meters_enabled`** on **`GET /api/chat/capabilities`** (or the meters response). |

---

## 1. The three rings

| # | Label (user-facing) | Measures | Data source (MVP → v2) |
|---|---------------------|----------|-------------------------|
| **1** | **This turn** | Fill of **what we are about to send** for the model: system + **stored history** + **current user turn** (incl. attachments if modeled). | **v1:** Update **after** `POST /api/chat/stream` completes (or mid-flight from last known assembly), using server-side size/token estimate. **v1.5:** `POST /api/chat/context-meters` with optional **`draft`** for live composer preview. **v2:** Optional client-side draft heuristic (chars × factor) labeled **estimate only**. |
| **2** | **Workspace** | Tightest **role** instruction assembly vs **budget** (Architect / Commander “Routing” / Critic “Review”) — same idea as Context & memory bars. | `context_engine_dashboard_payload` fields (`roles.*.rendered_chars` vs caps) from **local** `GET /api/workspace/context-snapshot` when eligible, else **cloud** `GET /api/context-engine` or project-scoped equivalent; include **`source`** in JSON. |
| **3** | **Thread** | How heavy the **persisted session** is vs a **defined ceiling** (not raw turn count alone). | **MVP ratio:** `approx_transcript_chars / thread_budget_chars` where `approx_transcript_chars` = sum of stored turn contents (server), `thread_budget_chars` = e.g. `compact_max_tokens × 4` from merged **memory_heist** session config **or** a fixed cap document constant; label **estimate**. **v2:** tokenizer-based if available. |

**Color thresholds (single scale, all rings):**

- **Green:** &lt; **60%**
- **Amber:** **60–85%**
- **Red:** &gt; **85%**

(Tunable after dogfood.)

---

## 2. UX

- **Placement (composer):** Match **Cursor-style** layout on the **bottom toolbar** of `WorkspaceChatComposer`: put the **three context rings on the bottom-right**, **immediately left of** voice and send (reading left → right: … **Turn | Workspace | Thread** · mic · send). Keeps “how hard is this request?” next to the actions that trigger it.
- **Unified toolbar controls:** Make **every** interactive control on that bottom row the **same size** (fixed width/height circle or rounded-square hit target)—**attach (+)** , **model selector** trigger height, **each meter ring** , **mic** , **send** . Today the mic can read larger than send; **normalize** so the row feels **one rhythm** (Cursor’s strip is visually even). Use one shared token (e.g. `size-9` / `40px`) for icon buttons; meters use the **same outer diameter** as those buttons with a thin stroke so they don’t dominate.
- **Narrow screens:** If the row doesn’t fit, collapse to **one** combined meter + **“+2”** overflow popover, or move meters into a **single** compact control—still **right-aligned** before send when possible.
- **Hover (max ~4 short lines):** (1) title + %, (2) one numeric line **with units** (`est. tokens`, `chars`, or `ratio`), (3) one-line “why,” (4) **one** action.
- **Link:** “Context & memory” → existing settings (same section users already trust).
- **A11y:** Text label or `aria-label` per ring; never rely on color alone.
- **Loading / degraded:** If a ring can’t be computed, show **gray** + tooltip “Unavailable” (not fake 0%).

### Copy bank (nudges)

- **This turn (high):** Shorten message, remove attachments, narrow the ask, or pick a **larger-context model** if available.
- **Workspace (high):** Open **Context & memory**; reduce instruction surface / split work; check **Routing** cap first if it’s the bottleneck.
- **Thread (high):** **New chat session**; export if needed; long threads are compacted or truncated.

---

## 3. API

**Preferred: `GET /api/chat/context-meters`**

Query: `session_id` (required for **Thread**), `model_id` (required for honest **This turn** limit), optional `project_id` if workspace ring uses project-scoped engine.

```json
{
  "enabled": true,
  "this_turn": {
    "fill_ratio": 0.68,
    "unit": "estimate_tokens",
    "used": 138300,
    "limit": 200000,
    "model_id": "…"
  },
  "workspace": {
    "fill_ratio": 0.92,
    "bottleneck_role": "commander",
    "source": "local"
  },
  "thread": {
    "fill_ratio": 0.45,
    "approx_transcript_chars": 48000,
    "thread_budget_chars": 106000
  }
}
```

- **Null** a subtree when unknown; UI skips or grays that ring.
- **Auth:** Same enforcement pattern as **`GET /api/chat/sessions`** (`enforce_clerk_session_and_email_for_request`).

**Optional: `POST /api/chat/context-meters`** (preview)

- Body: `{ "session_id", "model_id", "draft_plaintext"?: "…", "draft_attachments_meta"?: … }`
- Used only when live draft meter is worth the cost.

**Caching**

- Client debounce **≥ 400ms** on polls tied to typing if POST preview exists.
- Server: short TTL or in-process cache for **workspace** snapshot hash by `(root, config mtime)` if discovery is expensive.

---

## 4. Frontend

- Component: **`ContextMeterCluster`** (3 rings + overflow on small viewports), **same footprint** as adjacent icon buttons.
- **`WorkspaceChatComposer.tsx`**: mount the cluster in the **bottom-right toolbar group** (with voice + send); refactor toolbar so **attach**, **model picker**, **meters ×3**, **mic**, **send** share **one size system** (design + implementation pass—avoid oversized mic gradient orb breaking alignment).
- **WorkspaceChatScreen** / composer props: wire `sessionId`, **`model_id`**, poll **GET** on session/model change and **after stream done**; add **POST preview** only in v1.5+.
- **No duplicate truth:** Prefer one fetch feeding meters + avoid diverging from Context & memory numbers (same snapshot helper on backend if possible).

---

## 5. Rollout

1. **`HAM_CONTEXT_METERS=1`** on API; optional `context_meters_enabled` in capabilities for UI.
2. **Staging** dogfood: compare rings to **actual** truncation / bad outputs.
3. **Docs:** One short paragraph: what each ring means, that **Thread** / **This turn** may be **estimates**.

---

## 6. Phasing (blockers → order)

| Phase | Scope |
|-------|--------|
| **P0** | **Workspace** + **Thread** rings (no draft dependence). |
| **P1** | **This turn** **post-send** only + **model_id**-aware limit. |
| **P2** | **Draft preview** via POST or client heuristic. |
| **P3** | Tokenizer alignment, richer tooltips, analytics. |

---

## 7. Out of scope

- Replacing the Context & memory panel.
- Cursor-style per-rule lists in tooltip (optional later).
- Multi-repo merged meters in one ring.

---

## 8. Resolved open questions (MVP defaults)

| Question | MVP default |
|----------|-------------|
| Tokens vs chars | **Server estimate** for this turn; **chars** for thread; document `unit` in JSON. |
| Workspace on cloud-only user | **`source: "cloud"`**; show `/app`-style honesty in tooltip when applicable. |
| Thread ratio | **`approx_transcript_chars / thread_budget_chars`** with budget from merged **memory_heist** `compact_max_tokens × 4` (or single constant if config missing). |
