# CodingPlanCard Replacement Plan

Docs-only plan for removing or replacing the visible `CodingPlanCard` chat surface while **preserving** the approval/digest/launch mechanics it currently hosts. This document is the recommended next step after [Invisible Orchestration Phase 3](./INVISIBLE_ORCHESTRATION_PHASE_3_CHECKPOINT.md). It defines target UX, options, phases, tests, and risks. **It adds no implementation, backend, routing, or build-kit changes.**

**Baseline:** `origin/main` at `24479344` — `docs(builder): add invisible orchestration phase 3 checkpoint`.

---

## 1. Executive summary

- `CodingPlanCard` should **not** remain a prominent normal UX surface if it makes HAM feel like a **provider/router dashboard** instead of a conversation-first build tool.
- The visible **plan/candidate presentation** (provider rows, "Why this plan?", recommendation reasons, disabled placeholder button) can likely be **removed or collapsed** — it is mostly presentation.
- The **approval/digest/launch mechanics** are **not** in the card's presentation; they live in `ManagedProviderBuildApprovalPanel` (wrapped by `ManagedBuildApprovalPanel` for Droid and `ManagedOpencodeBuildApprovalPanel` for OpenCode). These **must be preserved** through any change.
- This document adds **no implementation**. It is a plan only.

---

## 2. Current baseline

- **Provider invisible orchestration complete** — OpenCode, Droid/Factory, Claude, and Cursor launch seams enrich runner prompts internally (see Phase 3 checkpoint).
- **Build-kit internals remain invisible** — recipe IDs, pack IDs, `registry_v2_app_type`, `fallback_reason`, gate reports, scaffold quality codes, YAML paths, render lengths, and playbook headers stay out of normal payloads, feeds, and UI copy.
- **Chat-first UX is the target** — chat is the primary build surface.
- **Right pane is the preferred preview/result/details area** — the workbench right pane is where build preview, status, and result should live.
- **Builder Studio remains non-surfaced / config-only** — it must **not** become a task-launch surface.

---

## 3. What CodingPlanCard currently does

Source: `frontend/src/features/hermes-workspace/screens/chat/coding-plan/CodingPlanCard.tsx`, mounted in `WorkspaceChatScreen.tsx` (`data-hww-coding-plan-card-wrap`).

| Responsibility | Detail | Disposition |
|----------------|--------|-------------|
| **Presentation** | Section header (`CODING_PLAN_SECTION_LABEL`), task-kind badge, builder badge, headline, plan description, impact line, approval-copy line | Mostly removable / collapsible |
| **Approval/launch host** | Conditionally mounts `ManagedBuildApprovalPanel` (Droid) or `ManagedOpencodeBuildApprovalPanel` (OpenCode) when `payload.project.project_id` is present and the provider applies | **Must be preserved** (relocate, do not delete) |
| **Provider candidate / reason display** | `CandidateRow` for each alternative, provider/output-kind badges, `Blocked` pill, per-candidate `reason` and `blockers`, "Why this plan?" toggle exposing `recommendation_reason` | Removable / hideable |
| **Disabled placeholder launch button** | Footer `Approve build` button rendered `disabled` (`data-launch-enabled="0"`) with `CODING_PLAN_NO_LAUNCH_FOOTER` when no managed approval panel applies | Removable |
| **Embedded managed approval panels** | The real preview→approve→launch flow is delegated to the managed panels, not the card | **Must be preserved** |
| **OpenCode affordance** | Optional "prefer OpenCode" CTA (`onPreferProvider`) | Reassess; keep only if still needed by product |

**Key audit finding:** the card's own JSX is presentation + a host shell. The disabled footer button is a placeholder, not a launch path. The actual mechanics are entirely inside `ManagedProviderBuildApprovalPanel`.

---

## 4. What can be removed or hidden

These are **presentation only** and carry no launch/digest mechanics:

- Provider / candidate rows (`CandidateRow`, `data-hww-coding-plan="candidate-row"`)
- "Why this plan?" explanation toggle (`alternatives-toggle` / `alternatives`)
- Recommendation reasons (`recommendation-reason`, `payload.recommendation_reason`)
- Blocker / alternative display **if not necessary** for user understanding (keep only genuinely actionable blockers)
- Visible provider-plan framing (section label, builder badge, provider/output-kind badges) that makes HAM look like a router dashboard
- Disabled placeholder launch button (`launch-cta-disabled`, `data-launch-enabled="0"`) and `no-launch-footer`

Removing these does **not** touch any approval, digest, or launch code path.

---

## 5. What must be preserved

These are required mechanics and must survive any relocation/removal:

- **`ManagedProviderBuildApprovalPanel`** — the generic engine, plus its wrappers `ManagedBuildApprovalPanel` (Droid) and `ManagedOpencodeBuildApprovalPanel` (OpenCode).
- **preview → approve checkbox → digest-verified launch** — the `idle → previewing → previewed → launching → running → succeeded/failed` state machine.
- **`confirmed: true` approval gate** — launch is only callable from `previewed` + `approved`; `confirmed: true` is sent on launch.
- **proposal digest validation** — `proposal_digest` + `base_revision` from the preview are passed unchanged into launch (server verifies the digest).
- **launch / polling state** — `running` phase polls `fetchControlPlaneRun(hamRunId)` until `succeeded` / `failed` / `cancelled`.
- **retry / failure handling** — failure phase with `startOver` reset; preview/launch error shortening; `SmokePreflightError` surfacing.
- **saved version / preview result wiring** — `SuccessSummary` (`preview_url`, `changed_paths_count`, `snapshot_id`, neutral outcome, technical-details `<details>`).
- **no build-kit internals exposure** — any new surface must keep recipe/pack/registry internals invisible (reuse existing sanitization; do not add new leak points).

---

## 6. Recommended UX target

- **Chat stays clean** — the conversation should read like a normal build chat, not a provider/route dashboard.
- **Right pane hosts build approval/status/result** — the workbench right pane is the natural home for preview, approval, live status, and the success summary.
- **Chat may show a short natural-language nudge** — e.g. "I can build this" or "Ready to build" — without provider/candidate/kit framing.
- **Approval appears as a slim action strip or right-pane card** — a compact "Preview / Approve / Build" affordance, not a full plan dashboard.
- **No provider/route/kit mechanics by default** — provider names, candidate reasons, and routing rationale are hidden unless an explicit advanced/operator surface is requested later.

---

## 7. Replacement options

| Option | Description | Pros | Risks | Recommendation |
|--------|-------------|------|-------|----------------|
| **A. Move approval panels to right pane** | Render `ManagedProviderBuildApprovalPanel` (preview/approve/launch/status/result) in the workbench right pane; chat only shows a short nudge | Cleanest chat; aligns with right-pane target; clear separation of conversation vs. build action | Highest effort; must wire prompt/project state into right pane; risk of duplicated state between chat and pane | **Long-term target** |
| **B. Replace CodingPlanCard with slim inline approval strip** | Drop the card shell; render only a compact inline approval strip in chat that still mounts the managed panel | Small, safe; preserves mechanics; removes dashboard framing | Still lives in chat (not right pane); interim only | **Recommended early step** (tie for smallest safe step) |
| **C. Keep card but strip provider/candidate details** | Keep the card container but remove candidate rows, "Why this plan?", recommendation reasons, disabled footer button | Smallest diff; mechanics untouched; reversible | Card framing remains; partial improvement only | **Recommended smallest first step** |
| **D. Hide card unless advanced/debug mode** | Gate the full card behind an operator/debug flag; normal users see slim approval only | Preserves diagnostics for operators | Adds mode/flag complexity (out of scope for now); risk of dead UI | Defer (Phase 5, optional) |
| **E. Remove conductor preview surfacing entirely** | Stop rendering the conductor preview/card in chat altogether | Maximally clean chat | Removes the only current approval entry point unless approval is relocated first; high regression risk | **Do not do before A** |

---

## 8. Recommended approach

- **Start with Option C or B** as the smallest safe step — strip provider/candidate presentation (C) and/or collapse to a slim inline approval strip (B) while leaving the managed approval panels mounted exactly as they are.
- **Long-term target is Option A** — relocate approval/status/result to the right pane so chat stays conversational.
- **Do not remove the approval panels until they are relocated** — Option E must never run before Option A lands; the managed panel is the only real launch path.
- **Do not touch conductor internals yet** — the coding conductor preview backend (recommender, no runner prompt) remains deferred; this plan only changes how its output is *presented*, not how it is computed.

---

## 9. Implementation phases

> Planning only — no phase below is authorized to start from this document.

- **Phase 1 — UI audit / test expectations.** Catalog every `data-hww-coding-plan="…"` hook and existing test assertion; define which selectors are presentation (safe to drop) vs. mechanics (must stay). Write/adjust test expectations *before* changing JSX.
- **Phase 2 — Slim card / strip replacement preserving approval panels.** Apply Option C/B: remove candidate rows, "Why this plan?", recommendation reasons, and the disabled footer button; keep `ManagedBuildApprovalPanel` / `ManagedOpencodeBuildApprovalPanel` mounting logic unchanged.
- **Phase 3 — Move approval/status to right pane.** Apply Option A: host `ManagedProviderBuildApprovalPanel` in the workbench right pane; chat shows only a short nudge; share a single source of truth for prompt/project to avoid duplicated state.
- **Phase 4 — Remove obsolete CodingPlanCard presentation.** Delete the now-unused card shell and copy constants once the right-pane surface is proven; keep managed panels and their wrappers.
- **Phase 5 — Optional debug/operator-only provider diagnostics.** If still wanted, expose candidate/reason details behind an explicit operator/debug surface (Option D) — never default-on, never leaking build-kit internals.

---

## 10. Tests needed

- Approval panel still renders when a managed build applies (Droid `managed_workspace`, OpenCode lane) for a project with `project_id`.
- Digest launch flow still works: `previewed` + `approved` → `launch({ confirmed: true, proposal_digest, base_revision })` → `running` → poll → `succeeded`/`failed`.
- Chat no longer shows provider candidate / reason details (no `candidate-row`, no `recommendation-reason`, no `Why this plan?`).
- No build-kit internals visible in chat, right pane, feed, or success summary (extend existing leakage guards).
- Right pane or slim strip shows preview / approval / result correctly (state transitions and success summary fields render).
- No Builder Studio / task-launch regression — Builder Studio remains non-surfaced/config-only; no new launch entry points there.
- Retry/failure: failure phase renders error + `startOver`; `SmokePreflightError` still surfaces its code/message.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Breaking the approval gate | Do not modify `ManagedProviderBuildApprovalPanel` state machine; only relocate where it mounts; assert `confirmed: true` gate in tests |
| Losing digest verification | Pass `proposal_digest` + `base_revision` from preview straight through to launch unchanged; add a regression test |
| Hiding important errors | Keep failure phase, error shortening, and `SmokePreflightError` surfacing in whichever surface hosts the panel |
| Duplicating state between chat and right pane | Single source of truth for prompt/project/preview state; chat nudge is display-only and does not own launch state |
| Exposing provider / build-kit internals | Reuse existing sanitization; remove (not relabel) candidate/reason presentation; extend leakage guards to the new surface |
| Accidental Builder Studio regression | Do not route any launch/approval through Builder Studio; keep it config-only; add a guard test |
| Removing the only approval entry point too early | Never apply Option E before Option A; gate Phase 4 on a proven right-pane surface |

---

## 12. Non-goals

- No implementation from this document.
- No backend changes.
- No provider orchestration changes.
- No routing changes.
- No build-kit changes (no recipes, packs, templates, registry/game-pack YAML, v1 JSON).
- No debug-mode implementation (Phase 5 is optional and out of scope here).
- No conductor internals changes (preview computation stays deferred).
- No default Build Registry v2 enablement.

---

## 13. References

| Document | Role |
|----------|------|
| [INVISIBLE_ORCHESTRATION_PHASE_3_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_PHASE_3_CHECKPOINT.md) | Phase 3 closeout; recommends this plan as the next step |
| [INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md](./INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md) | Product/UX posture — conversation-first, invisible kits |
| [INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md](./INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md) | Minimal phased implementation plan for provider seams |
| [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md) | Strategic next-wave framing |

**Frontend touchpoints (for the eventual implementer; no changes made here):**

- `frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx` — mounts `CodingPlanCard` (`data-hww-coding-plan-card-wrap`)
- `frontend/src/features/hermes-workspace/screens/chat/coding-plan/CodingPlanCard.tsx` — presentation + approval host shell
- `frontend/src/features/hermes-workspace/screens/chat/coding-plan/ManagedProviderBuildApprovalPanel.tsx` — generic preview/approve/launch/poll engine (**preserve**)
- `frontend/src/features/hermes-workspace/screens/chat/coding-plan/ManagedBuildApprovalPanel.tsx` — Droid wrapper (**preserve**)
- `frontend/src/features/hermes-workspace/screens/chat/coding-plan/ManagedOpencodeBuildApprovalPanel.tsx` — OpenCode wrapper (**preserve**)
- `frontend/src/features/hermes-workspace/workbench/WorkspaceWorkbench.tsx` — right-pane target for Option A
- `frontend/src/lib/ham/api.ts` — preview/launch/`fetchControlPlaneRun` client helpers
