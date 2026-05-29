# Invisible Build Kit Orchestration Plan

Planning artifact for using Build Registry v2 build kits **invisibly** inside HAM's conversation-first product flow. This document defines the product/UX posture only — it is **not** approval for runtime implementation, recipes, routing, frontend/API changes, default v2 enablement, or any Builder Studio task-launch surface. Build-kit internals stay invisible to normal users. For live status see [STATUS.md](STATUS.md).

**Baseline:** `origin/main` at `9b53a210` — `docs(builder): add next wave decision`.

---

## 1. Executive summary

- **Build kits should improve output quality invisibly** — HAM selects and applies kits backstage to produce better results.
- **Normal users should not see kit names, routing explanations, gate reports, YAML mechanics, or internal build-kit metadata by default.**
- **The experience remains conversation-first** — users ask naturally, HAM plans/builds/results through chat with a supporting right-side pane.
- **This doc adds no runtime changes, recipes, routing, or UI implementation** — it is product/UX direction only.

---

## 2. Current baseline

| Field | Value |
|-------|--------|
| **Game-kit phase** | **Complete** — 16 recipes / 376 modules (DOM-native phase closed) |
| **Website-pack foundation** | **Complete** — `site.landing-page-core` + `site.dashboard-ui-core`, 59 modules |
| **`site.landing-page-core` final gate** | **Pass** |
| **`site.dashboard-ui-core` final gate** | **Pass** |
| **v1 default** | Preserved — Lane A uses existing Builder Kit JSON when flag is off |
| **v2 opt-in** | **`HAM_BUILD_REGISTRY_V2_ENABLED`** must be truthy for routing metadata and v2 playbook context |
| **Generated output** | **Not committed** — gate artifacts under `/tmp/` only |
| **Builder Studio** | **Not a primary user-facing execution area** — routes redirect to Settings → Builders (config-only); build initiation lives in chat |

---

## 3. Product UX principle

- **The user asks naturally** — no command syntax, no kit picker.
- **HAM plans, builds, and returns results through chat.**
- **The right-side pane shows useful preview/output** — the polished artifact, not the machinery.
- **Internal orchestration stays backstage** — kit selection, routing, and gating are not narrated to the user.
- **No visible "selected kit" or "routing matched" detail for normal users.**
- **No gate reports** unless a future, explicitly-gated developer/debug/operator mode exists.

---

## 4. What users should see

Users should see:

- A **concise plan** (only when it adds clarity).
- A **preview** of what will be / was built.
- A **result summary** in plain language.
- **Revision options** (retry, revise, simplify).
- **Errors phrased in plain language.**
- **Approval prompts only when needed** (e.g. when execution genuinely requires a gate).

Users should **not** see:

- Recipe IDs (e.g. `site.dashboard-ui-core`)
- Pack IDs (e.g. `pack.site`)
- Route-matching details ("matched dashboard intent", confidence scores)
- Gate checklist details
- Scaffold-quality issue codes (e.g. `dashboard_dead_filter_control`)
- Registry metadata (`registry_v2_app_type`, render lengths)
- YAML references or module names

---

## 5. What internal systems may track

Backstage / operator-only, never surfaced by default:

- Selected app type (recipe id)
- Routing confidence / match strength
- Fallback reason (why v1 vs v2, why no match)
- Generated gate outcome (Pass / Conditional / Hold)
- Repair loops (issues detected, repair attempts)
- Build artifacts (generated files, locations)
- Preview links
- Audit logs
- Operator/debug-only metadata

---

## 6. Conversation-first flow

1. **User asks in chat** — natural language intent.
2. **HAM interprets intent.**
3. **Internal build-kit selection happens silently** — routing/kit choice is backstage.
4. **HAM gives a short natural-language plan** only if it helps.
5. **User approves or revises.**
6. **HAM builds.**
7. **Right pane shows preview / result.**
8. **Chat summarizes outcome and next options.**

At no step are kit names, routing rationale, or gate internals narrated to a normal user.

---

## 7. Right-side pane role

The right-side pane may show:

- **Preview** of the build
- **File / change summary**
- **Build result**
- **Approval state**
- **Retry / revise controls**

The right-side pane must **not** show:

- Raw routing details or match explanations
- Gate reports or checklist internals
- Registry/kit metadata for normal users

---

## 8. Settings/config role

- **Builder connections may remain Settings-only** (read-only connection/config status).
- **No task-launch controls** in Settings — work starts in chat.
- **No Build Kit catalog** for normal users.
- **Config surfaces should reinforce that work starts in chat** (e.g. existing "Builders are configured here. Work starts in chat." copy).

---

## 9. Internal/debug/operator mode boundary

- A **future developer/debug/operator mode** may expose kit metadata (selected kit, routing confidence, gate outcome, repair logs).
- It must be **disabled by default**.
- It is **not part of normal UX**.
- It exists **only for troubleshooting, QA, or internal operators** — gated behind an explicit flag/role, never shown to normal users.

---

## 10. Failure handling

**When no kit matches:**

- Fall back gracefully (v1 default path).
- Ask a clarifying question only when genuinely needed.
- **Do not say "no route matched"** or expose routing internals.
- Offer plain-language alternatives ("I can build this as a simple page — want me to proceed?").

**When a quality gate / repair fails:**

- **Do not show gate internals** (issue codes, checklist, scaffold-quality detectors).
- Explain in user terms ("I tidied up the layout but a couple of details need your call").
- Offer **retry / revise / simplify** options.

---

## 11. Anti-patterns to avoid

- A **visible kit catalog** as primary UX.
- A **Builder Studio task-launch surface** (re-surfacing build execution outside chat).
- **Gate reports in normal UI.**
- **Route/debug explanations in chat.**
- **Overwhelming users with internal plan details.**
- **Exposing YAML / build-kit mechanics.**
- **Pretending internal confidence is user-facing truth** (e.g. surfacing routing confidence as if it were a guarantee).

---

## 12. Recommended implementation posture

No implementation is authorized by this doc. If/when implementation begins, future work should:

- **Preserve the conversation-first UX.**
- **Use build kits silently** — selection and gating stay backstage.
- **Keep metadata internal** — operator/debug only, off by default.
- **Surface results, not machinery.**
- **Add tests that assert no accidental user-facing kit exposure** (no recipe/pack IDs, gate codes, or registry metadata leaking into normal chat/right-pane copy).

---

## 13. Non-goals

This plan does **not** authorize or implement:

- Runtime implementation from this doc
- Frontend changes
- API changes
- Builder Studio surfacing as a build execution area
- Recipe or routing changes
- CI changes
- Debug/operator mode implementation
- Enabling Build Registry v2 by default
- Exposing build-kit internals to normal users

---

## 14. References

- [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md)
- [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md)
- [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](./LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md)
- [DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md](./DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md)
- [STATUS.md](./STATUS.md)
