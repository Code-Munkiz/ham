# Right Pane Approval and Status Relocation Plan

Docs-only product/UX implementation plan for relocating build **approval / status / result** surfaces toward the workbench **right pane**, while keeping **chat clean and conversation-first**. This is the dedicated plan called for as Option A in [CODING_PLAN_CARD_REPLACEMENT_PLAN.md](./CODING_PLAN_CARD_REPLACEMENT_PLAN.md) and deferred follow-up "B" in [INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md). It defines product posture, target right-pane states, a phased path, tests, and risks. **It adds no implementation, runtime, API, routing, frontend, Builder Studio, scaffold, v1 JSON, template, recipe YAML, registry YAML, or game-pack YAML changes.**

**Baseline:** `origin/main` at `e725129c` — `docs(builder): add app surface domain stage checkpoint`.

**App-surface / domain wave:** complete — `site.landing-page-core`, `site.dashboard-ui-core`, `app.saas-dashboard-core`, `app.admin-dashboard-core`, `app.sales-ops-dashboard-core` (all final gate **Pass**). See [APP_SURFACE_DOMAIN_STAGE_CHECKPOINT.md](./APP_SURFACE_DOMAIN_STAGE_CHECKPOINT.md).

---

## 1. Executive summary

- **Goal:** move the build **approval / status / result** UX toward the workbench **right pane**, where preview and results naturally live.
- **Chat remains conversational and clean** — it is the command/intent surface, not a provider/router dashboard.
- **The right pane becomes the preview / result / action surface** — preview, approval-when-required, live status, and result actions live there.
- **This plan adds no implementation** — it is planning and direction only.
- **Build-kit internals remain invisible** to normal users (recipe IDs, pack IDs, routing metadata, gate language, YAML, render budgets all stay backstage).

---

## 2. Current baseline

- **Build kits now work backstage.** All four provider launch seams (OpenCode, Droid/Factory, Claude, Cursor) enrich runner prompts internally when `HAM_BUILD_REGISTRY_V2_ENABLED` is on and v2 resolves; v1/default is preserved when the flag is off or no app type resolves (see [INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md)).
- **Provider launch seams are invisible.** Recipe IDs, pack IDs, `registry_v2_app_type`, `fallback_reason`, gate reports, scaffold-quality issue codes, YAML paths, render lengths, and playbook headers stay out of normal payloads, mission feeds, summaries, and UI copy.
- **`CodingPlanCard` has been simplified.** Per [CODING_PLAN_CARD_REPLACEMENT_PLAN.md](./CODING_PLAN_CARD_REPLACEMENT_PLAN.md) Option C/B, the card now shows a minimal "Ready to build" surface instead of provider candidate rows, "Why this plan?", recommendation reasons, or a disabled placeholder launch button.
- **Managed approval panels still preserve important launch mechanics.** The real preview → approve → digest-verified launch flow lives in `ManagedProviderBuildApprovalPanel.tsx` and its wrappers `ManagedBuildApprovalPanel.tsx` (Droid) and `ManagedOpencodeBuildApprovalPanel.tsx` (OpenCode). These are unchanged.
- **Preview / result UX naturally belongs in the right pane.** The workbench right pane (`frontend/src/features/hermes-workspace/workbench/WorkspaceWorkbench.tsx`) is already the preview/result area; the approval/status/result surfaces are the missing pieces that still partly live in chat.

---

## 3. Product principle

- **Chat = ask, guide, revise.** Natural-language intent, short confirmations, brief outcome summaries. No provider/router/kit framing.
- **Right pane = preview, approve when needed, status, result actions.** The right pane hosts the visual artifact, a slim approval/action area only when a gate is genuinely required, live build status, and result affordances.
- **Internals = hidden.** Build-kit names, routing rationale, gate reports, and YAML mechanics never surface to normal users.
- **Builder Studio is not a primary task-launch surface.** It remains config-only / non-surfaced; this plan must not reintroduce it as a build initiation point.

---

## 4. What users should see

- A **short chat confirmation** when a build is understood (e.g. "I can build this — preview's on the right").
- A **preview on the right** of what will be / was built.
- A **simple build status** (preparing, building, refining, done) in plain language.
- A **clean approve/continue action only when required** — a slim action area, not a dashboard.
- **Revise / retry / open / export actions** where appropriate, in the right pane.
- **Plain-language failure states** ("Something went wrong building this — want me to try again?") with a retry/revise path.

---

## 5. What users should not see

Normal users must **not** see, in chat or the right pane:

- **Build-kit names** (e.g. "landing page core" kit framing)
- **Recipe IDs** (e.g. `site.dashboard-ui-core`, `app.saas-dashboard-core`)
- **Routing confidence** / match strength
- **Fallback reasons** (why v1 vs v2, why no match)
- **YAML modules** / module names / paths
- **Gate reports** / gate review language
- **Scaffold-quality issue codes** (e.g. `dashboard_`, `landing_`, `tactics_` prefixes)
- **Provider candidate matrices** (candidate rows, alternatives, "Why this plan?")
- **Repair-loop details** (issues detected, repair attempts, escalated passes)
- **Internal logs** as user-facing copy
- **Builder Studio execution controls**

---

## 6. Existing mechanics to preserve

Any relocation must preserve these mechanics **exactly** — relocate where they mount, never reimplement or weaken them:

- **`ManagedProviderBuildApprovalPanel`** (or equivalent approval engine) — the generic preview/approve/launch/poll engine, plus wrappers `ManagedBuildApprovalPanel` (Droid) and `ManagedOpencodeBuildApprovalPanel` (OpenCode).
- **Preview before launch** — the `idle → previewing → previewed → launching → running → succeeded/failed` state machine.
- **Approval checkbox / confirmation gate** if still needed — launch only callable from `previewed` + `approved`.
- **`confirmed: true` server gate** — sent on launch; server enforces it.
- **`proposal_digest`** — passed unchanged from preview into launch.
- **`base_revision`** — passed unchanged from preview into launch.
- **Digest verification** — server verifies `proposal_digest` + `base_revision`; the client must not bypass it.
- **Launch polling** — `running` phase polls `fetchControlPlaneRun(hamRunId)` until terminal status.
- **Control-plane run fetching** — the `fetchControlPlaneRun` lifecycle that drives status.
- **Retry / failure handling** — failure phase with `startOver` reset; preview/launch error shortening; `SmokePreflightError` surfacing.
- **Success summary / result wiring** — `SuccessSummary` (`preview_url`, `changed_paths_count`, `snapshot_id`, neutral outcome, technical-details `<details>`).

---

## 7. Target right-pane states

The right pane should express a small, well-defined set of states. In every state, build-kit internals stay hidden.

### Empty / idle
- **Right pane:** neutral placeholder / current project preview; no build affordances.
- **Chat:** conversational; no build surface mounted.
- **User actions:** ask in chat to build/change something.
- **Hidden internals:** all (no kit/routing/gate metadata anywhere).

### Preview ready
- **Right pane:** rendered preview of the proposed build; slim "what this is" framing in plain language.
- **Chat:** short confirmation ("Preview's on the right").
- **User actions:** review preview; proceed / revise.
- **Hidden internals:** recipe/pack IDs, routing rationale, render budgets, playbook headers.

### Approval required
- **Right pane:** slim approval/action area (confirm/approve), preview still visible; carries the existing `confirmed: true` + digest gate.
- **Chat:** short nudge only ("Ready when you are — approve on the right").
- **User actions:** approve/confirm, or revise via chat.
- **Hidden internals:** digest value framing, base revision, provider candidate detail.

### Building
- **Right pane:** simple progress/status indicator driven by `fetchControlPlaneRun` polling; plain-language phase.
- **Chat:** quiet or a single "Building…" acknowledgement; no log stream.
- **User actions:** wait; optional cancel if already supported.
- **Hidden internals:** polling internals, run IDs, provider mechanics, repair loops.

### Repairing / refining
- **Right pane:** plain-language "refining the result" status; no issue codes or gate detail.
- **Chat:** quiet or brief reassurance.
- **User actions:** wait.
- **Hidden internals:** repair-loop counts, scaffold-quality issue codes, escalated-pass detail, gate outcomes.

### Completed
- **Right pane:** result preview + `SuccessSummary` affordances (open/export/revise); neutral outcome copy.
- **Chat:** brief outcome summary ("Done — it's on the right. Saved N changes." level, no internals).
- **User actions:** open, export, revise, retry/build again.
- **Hidden internals:** snapshot mechanics beyond neutral counts, technical details kept in a collapsed `<details>`.

### Failed recoverably
- **Right pane:** plain-language failure + retry/revise action (`startOver`); preserves `SmokePreflightError` surfacing in a user-friendly way.
- **Chat:** short, plain-language failure + offer to retry/revise.
- **User actions:** retry, revise, simplify.
- **Hidden internals:** stack traces, raw error payloads, gate/repair internals (shortened error only).

### Failed terminally
- **Right pane:** plain-language "couldn't complete this" with a clear next step (revise approach / try a simpler build).
- **Chat:** brief, honest, non-technical explanation; no "route matched" / "gate failed" language.
- **User actions:** revise approach in chat; start a different build.
- **Hidden internals:** all diagnostics; no raw logs.

---

## 8. Recommended UX flow

1. **User asks in chat** to build something (natural language).
2. **HAM acknowledges naturally** — short confirmation, no provider/kit framing.
3. **Preview appears in the right pane.**
4. **If approval is required, the right pane shows a slim approval/action area** carrying the existing digest/confirmation gate.
5. **Build status appears in the right pane** (preparing → building → refining), driven by control-plane run polling.
6. **Result preview appears in the right pane** with open/export/revise affordances.
7. **Chat summarizes the outcome briefly** (plain language, no internals).
8. **User revises through chat or a right-pane action**, looping back to step 3.

---

## 9. Minimal implementation path

> Planning only — no phase below is authorized to start from this document. Keep **one tiny PR per phase**.

### Phase 0 — audit only
- Map current preview / approval / status / result components (`CodingPlanCard.tsx`, `ManagedProviderBuildApprovalPanel.tsx`, Droid/OpenCode wrappers, `WorkspaceWorkbench.tsx`).
- Identify the exact owner of approval mechanics (state machine, `confirmed: true` gate, digest pass-through, polling).
- Identify the right-pane host surface and how it receives prompt/project state.
- **No behavior change.** Output is a component/ownership/test-coverage map.

### Phase 1 — right-pane status shell
- Add or identify a right-pane build **status container** (Empty/idle → Building → Completed/Failed display shell).
- **No approval relocation yet.**
- **No API contract changes** unless strictly required (prefer reusing existing `fetchControlPlaneRun`).

### Phase 2 — approval panel relocation
- Render the **existing** managed approval panel inside the right pane (do not fork or reimplement it).
- **Preserve digest / confirmation / launch behavior exactly** (`proposal_digest`, `base_revision`, `confirmed: true`, polling).
- The chat card becomes a **minimal pointer only** ("approve on the right"); single source of truth for prompt/project/preview state to avoid duplicated launch state.

### Phase 3 — result/action consolidation
- Move **retry / open / export / revise** affordances into the right pane (reuse `SuccessSummary` + failure/`startOver`).
- Chat gives **short outcome summaries only**.

### Phase 4 — cleanup
- Remove obsolete chat presentation once the right-pane surface is proven.
- Keep / extend tests that guard against accidental internal leakage and against losing the approval/digest/launch gate.

---

## 10. Testing posture

- **Approval / digest / launch tests must remain intact** — preview → `previewed` + `approved` → `launch({ confirmed: true, proposal_digest, base_revision })` → `running` → poll → `succeeded` / `failed`.
- **Frontend visible-copy tests must assert no build-kit internals** in chat or the right pane (no recipe/pack IDs, `registry_v2_app_type`, gate language, issue codes, YAML paths, render budgets, playbook headers).
- **Right-pane state tests** — each target state (idle, preview ready, approval required, building, repairing, completed, failed recoverably, failed terminally) renders correctly.
- **Chat remains concise** — no candidate rows / "Why this plan?" / recommendation reasons reappear; chat shows nudges and brief summaries only.
- **Failure states are plain-language** — no "route matched" / "gate failed" / raw logs; `SmokePreflightError` still surfaces in a user-friendly form.
- **No Builder Studio task-launch surfacing** — Builder Studio stays config-only; guard test if its surface is touched.
- **No provider / kit metadata leakage** into the new right-pane surface, feeds, or summaries (extend existing leakage guards to the relocated surface).

---

## 11. Risk review

- **Accidentally breaking digest launch mechanics** — relocating the panel could disturb `proposal_digest` / `base_revision` / `confirmed: true` pass-through. Mitigate: do not modify the state machine; relocate only where it mounts; assert the gate in regression tests.
- **Duplicating approval controls** — chat pointer + right-pane panel could both expose an approve action. Mitigate: a single owner of launch state; chat is display-only.
- **Surfacing internals in the right pane** — a richer right-pane surface increases leakage surface. Mitigate: reuse existing sanitization; extend leakage guards to the right pane.
- **Making the right pane feel like Builder Studio** — too many controls turns the pane into a provider dashboard. Mitigate: keep it slim; preview + minimal action + status + result only.
- **Hiding too much status from the user** — over-cleaning could leave users unsure if anything is happening. Mitigate: always show a simple plain-language status during Building/Repairing.
- **Confusing chat / right-pane ownership** — unclear which surface owns approval. Mitigate: right pane owns approval/status/result; chat owns intent/summary.
- **Mobile responsiveness** — a side-by-side right pane may collapse on small screens. Mitigate: define mobile behavior (see open question) before Phase 2 lands.

---

## 12. Anti-patterns

- A **giant technical build card in chat** (provider/router dashboard framing).
- A **provider dashboard in the right pane** (candidate matrices, provider rows).
- **Visible kit / routing / gate diagnostics** anywhere in normal UX.
- **Duplicate approve buttons** across chat and right pane.
- **Approval without digest verification** (any shortcut around `confirmed: true` + digest).
- **Status logs as user-facing copy** (raw polling/run logs shown to users).
- **Exposing the repair loop or scaffold issue codes** as user-facing detail.
- **The right pane becoming Builder Studio** (a task-launch execution surface).

---

## 13. Open questions

- Does approval need an **explicit checkbox**, or can it become a simpler "**Build this preview**" action while still sending `confirmed: true` + digest?
- **Which providers currently share the approval panel** (Droid via `ManagedBuildApprovalPanel`, OpenCode via `ManagedOpencodeBuildApprovalPanel`) — and do Claude/Cursor go through the same generic engine or a different lifecycle?
- Does **Cursor use the same right-pane lifecycle** (preview → approve → poll → result), or a different managed-mission projection that needs its own state mapping?
- **Which actions belong in chat vs. the right pane** (e.g. should "revise" be a chat message, a right-pane button, or both)?
- **How should mobile handle the right pane** (overlay, bottom sheet, full-screen takeover on build)?
- Should there be a **hidden operator/debug mode later** for kit/routing/gate diagnostics (off by default, never normal UX)?

---

## 14. Recommended next step

- **Start with Phase 0 audit.** Produce the component / ownership / test-coverage map first.
- **Do not implement relocation until the audit confirms** component ownership (who owns the approval state machine + digest/launch gate) and existing test coverage.
- **Keep one tiny PR per phase** — status shell, then approval relocation, then result consolidation, then cleanup.

---

## 15. Non-goals

- **No implementation** from this plan.
- **No API changes.**
- **No routing changes.**
- **No build-kit recipe changes** (no recipes, packs, templates, registry/game-pack YAML, v1 JSON).
- **No Builder Studio surfacing** as a task-launch area.
- **No debug/operator mode** implementation.
- **No provider replacement** or provider orchestration changes.

---

## 16. References

- [INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md](./INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md)
- [INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md](./INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md)
- [CODING_PLAN_CARD_REPLACEMENT_PLAN.md](./CODING_PLAN_CARD_REPLACEMENT_PLAN.md)
- [INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md)
- [APP_SURFACE_DOMAIN_STAGE_CHECKPOINT.md](./APP_SURFACE_DOMAIN_STAGE_CHECKPOINT.md)
