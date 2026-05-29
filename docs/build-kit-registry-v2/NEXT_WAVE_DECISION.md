# Build Registry v2 Next Wave Decision

Decision-framing artifact after the **website-pack foundation stage** completed on `origin/main`. This document frames the next-wave choice for Build Registry v2 — it is **not** approval for a new recipe, routing, product UI, or runtime change, and it does **not** enable Build Registry v2 by default. Build-kit internals remain invisible to normal users. For live status see [STATUS.md](STATUS.md).

**Baseline:** `origin/main` at `d2e40579` — `docs(builder): add website pack stage checkpoint`.

---

## 1. Executive summary

**The current foundation is complete; the next wave should be chosen deliberately.**

- The DOM-native game-kit phase and the website-pack foundation stage are both complete and pushed.
- The next workstream is a **strategic choice**, not an automatic continuation — pick before authoring anything.
- **No recipe, routing, product UI, or runtime changes are authorized by this doc.**
- **Build-kit internals remain invisible to normal users** — HAM uses kits internally and delivers polished results through the conversational flow and right-side preview/results pane.

---

## 2. Current baseline

| Field | Value |
|-------|--------|
| **Game-kit phase** | **Complete** — 16 recipes / 376 modules (DOM-native phase closed) |
| **Website-pack foundation** | **Complete** — `site.landing-page-core` + `site.dashboard-ui-core`, 59 modules |
| **`site.landing-page-core` final gate** | **Pass** |
| **`site.dashboard-ui-core` final gate** | **Pass** |
| **Stage checkpoint** | [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md) on `origin/main` |
| **v1 default** | Preserved — Lane A uses existing Builder Kit JSON when flag is off |
| **v2 opt-in** | **`HAM_BUILD_REGISTRY_V2_ENABLED`** must be truthy for routing metadata and v2 playbook context |
| **Generated output** | **Not committed** — gate artifacts under `/tmp/` only |
| **Templates / starter files** | **None** — generative playbooks only |

---

## 3. Product UX principle

The product direction governs how (and whether) any of this reaches users:

- **Users interact through a conversation-first build flow** — build initiation happens in chat, not in a dedicated builder execution surface.
- **The right-side pane may show preview / results / approval details** — the polished outcome and revision options, not internal mechanics.
- **No build-kit catalog, route explanations, gate reports, or YAML mechanics for normal users** — kit names, routing rationale, and gate decisions are not surfaced by default.
- **Internal metadata is allowed for operators/debugging** — diagnostics and audit can expose mechanics behind the scenes.
- **Settings-only builder configuration may remain internal/config** — e.g. Settings → Builders read-only connection status, with work still starting in chat.

---

## 4. Candidate next paths

| Path | Description | Pros | Risks | Recommended posture |
|------|-------------|------|-------|---------------------|
| **A. Invisible chat-flow integration polish** | Make internal kit selection quietly improve chat-driven build outputs; user sees plan/preview/result/revision, never kit internals | Directly advances product UX; no new recipe risk; leverages existing kits | Requires careful seam between routing metadata and user-facing copy; must not leak internals | **Strong candidate** — product-first, low recipe risk |
| **B. `app.saas-dashboard-core` research/readiness** | Research + readiness for the next bounded app-surface dashboard sibling | Natural step up from read-only dashboard UI core; reuses dashboard doctrine | Higher scope than read-only core; must stay bounded; no schema until readiness approved | Research/readiness only, if expanding kits |
| **C. `app.admin-dashboard-core` research/readiness** | Research + readiness for an admin/CRUD dashboard lane | Covers a common real-world surface | CRUD/auth/permissions risk; highest scope-drift danger | **Not first** — needs explicit CRUD/auth/permissions readiness before any other admin work |
| **D. Website-pack docs/status polish** | Align README/STATUS cross-links and wording; no new recipes | Safe, low effort, keeps docs accurate | Minimal product value on its own | Safe filler; not a strategic wave |
| **E. Pause build-kit expansion, switch to product UX work** | Stop adding kits; invest in conversational delivery and right-pane experience | Maximizes user-visible value of existing kits | Defers catalog breadth | Reasonable if product UX is the priority |

---

## 5. Recommendation

- **Do not author another recipe immediately.**
- **First decide** between **invisible chat-flow integration polish (Path A / E)** and the **next dashboard sibling research (Path B)**.
- **If continuing build kits**, research/readiness **must precede any schema** — same proven rhythm used for landing and dashboard lanes.
- **Admin/CRUD (Path C) should not be first** without an explicit, dedicated readiness review covering CRUD, auth, and permissions.

---

## 6. If choosing invisible chat-flow integration

Scope (product-first, no new recipe):

- Make **internal kit selection quietly improve outputs** — routing/kit choice happens behind the scenes.
- The user sees a **concise build plan, preview, result, and revision options** in the conversational flow + right-side pane.
- **No kit names or internal mechanics by default** — no catalog, routing rationale, or gate reports surfaced to normal users.
- **No Builder Studio task-launch surface** — build initiation stays in chat; Builder Studio is not a primary execution area.

This path would be planned in a dedicated doc (see § 9), not implemented from this decision artifact.

---

## 7. If choosing next dashboard sibling

Comparison of the two most likely siblings:

| Lane | Scope | Readiness needs |
|------|-------|-----------------|
| **`app.saas-dashboard-core`** | Bounded SaaS app-surface dashboard, a step up from read-only UI core | Separate research + readiness; keep bounded; define exclusions vs admin/CRUD |
| **`app.admin-dashboard-core`** | Admin dashboard with CRUD/auth/permissions | CRUD/auth/permissions readiness **first**; highest scope-drift risk |

Recommendation:

- **`app.saas-dashboard-core` is likely safer to research before `app.admin-dashboard-core`.**
- **`app.admin-dashboard-core` needs CRUD/auth/permissions readiness first** — do not start it cold.
- **Both require separate research/readiness docs** before any schema work.

---

## 8. Non-goals

This decision artifact does **not** authorize or implement:

- A new recipe from this doc
- Routing changes from this doc
- Runtime / API / frontend changes
- CI changes
- Templates or starter source files
- Committing generated output from `/tmp/`
- User-facing build-kit internals (kit names, routing details, gate reports, YAML mechanics)
- Builder Studio surfacing as a primary build execution area
- Enabling Build Registry v2 by default

---

## 9. Recommended next action

Choose one:

| If priority is… | Next action |
|-----------------|-------------|
| **Product direction first** | Create `INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md` (plan the invisible chat-flow integration; no implementation) |
| **Build-kit expansion first** | Create `SAAS_DASHBOARD_CORE_RESEARCH.md` (research the next dashboard sibling; no schema) |
| **Cautious** | Stop here and ask for a strategic decision before creating either follow-up |

In all cases, **research/readiness precedes schema**, and **no recipe is authored without an approved readiness review**.

---

## 10. References

- [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md)
- [DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md](./DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md)
- [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](./LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md)
- [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md)
- [STATUS.md](./STATUS.md)
