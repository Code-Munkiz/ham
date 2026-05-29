# Invisible Orchestration + Chat UX Cleanup Checkpoint

Combined closeout checkpoint after **invisible Build Kit orchestration** (all four provider launch seams) and the **CodingPlanCard chat UX cleanup** landed on `origin/main`. This document records the completed backend/internal enrichment work plus the frontend presentation simplification, and confirms that approval/digest/launch mechanics remain intact. This checkpoint is **not** approval for new recipes, routing, templates, runtime default v2 enablement, conductor preview changes, Builder Studio surfacing, or further implementation without explicit review. Build-kit internals remain invisible to normal users. For live registry status see [STATUS.md](STATUS.md).

**Baseline:** `origin/main` at `ddc2da9b` — `feat(chat): simplify coding plan approval surface`.

**Provider orchestration baseline:** `ed46a156` — `feat(builder): apply invisible orchestration to cursor launch` (Phase 3 closeout).

**Chat UX cleanup:** `ddc2da9b` — `feat(chat): simplify coding plan approval surface`.

**Prior guardrails:** `290bf883` — `test(builder): guard against build kit internals exposure`.

---

## 1. Executive summary

- **Invisible orchestration provider seams are complete** — OpenCode, Droid/Factory, Claude, and Cursor launch paths enrich runner prompts internally when `HAM_BUILD_REGISTRY_V2_ENABLED` is on and v2 resolves.
- **Normal users do not see build-kit internals** — recipe IDs, pack IDs, routing metadata, gate language, YAML paths, render budgets, playbook headers, and provider-echoed registry copy stay out of normal API payloads, mission feeds, summaries, and UI copy.
- **`CodingPlanCard` was simplified** to remove provider-plan/candidate presentation — the card now shows a minimal build-ready/approval surface instead of a provider/router dashboard.
- **Approval/digest/launch mechanics remain preserved** — `ManagedProviderBuildApprovalPanel` and its Droid/OpenCode wrappers are unchanged; preview → approve → digest-verified launch flow is intact.
- **This checkpoint adds no code, routing, recipes, templates, or runtime changes** — documentation only.

---

## 2. Current baseline

| Field | Value |
|-------|--------|
| **Latest pushed commit** | `ddc2da9b` — `feat(chat): simplify coding plan approval surface` |
| **Phase 1 OpenCode seam** | Complete on `origin/main` at `a7cc1c4e` |
| **Phase 2 Droid seam** | Complete on `origin/main` at `52774a89` |
| **Phase 3 Claude seam** | Complete on `origin/main` at `b54de596` |
| **Phase 3 Cursor seam** | Complete on `origin/main` at `ed46a156` |
| **Chat UX cleanup** | Complete on `origin/main` at `ddc2da9b` |
| **Build-kit guardrails** | `290bf883` — backend conductor/droid/opencode preview + frontend leakage tests |
| **v2 opt-in** | **`HAM_BUILD_REGISTRY_V2_ENABLED`** must be truthy for internal v2 playbook context on launch paths |
| **v1 default** | Preserved — flag off, no resolved app type, or v2 resolution failure leaves original prompt unchanged |
| **Conversation-first UX** | Preserved — chat is the primary build surface; no kit picker, catalog, or routing narration |
| **Builder Studio** | Remains non-surfaced / config-only |

---

## 3. Provider seam completion table

| Provider | Status | Internal enrichment | Exposure guard |
|----------|--------|---------------------|----------------|
| **OpenCode** | Complete (Phase 1) | `_enrich_internal_launch_prompt` in `src/api/opencode_build.py`; applied before `run_opencode_mission` | Launch `summary` / `error_summary` sanitization |
| **Droid / Factory** | Complete (Phase 2) | `_enrich_internal_launch_prompt` in `src/api/droid_build.py`; applied after digest verification, before `execute_droid_build_workflow` | Launch `summary` / `error_summary` sanitization |
| **Claude** | Complete (Phase 3) | `_enrich_internal_launch_prompt` in `src/api/claude_agent_build.py`; applied after digest verification, before `run_claude_agent_mission` | Launch `summary` / `error_summary` sanitization |
| **Cursor** | Complete (Phase 3) | `_enrich_internal_launch_prompt` in `src/ham/cursor_agent_workflow.py`; applied after digest verification, before `cursor_api_launch_agent` | Launch/status summary sanitization **plus** mission-feed/public-payload sanitization in `src/ham/cursor_provider_adapter.py` and `src/api/cursor_managed_missions.py` |

All four seams follow the same pattern: `select_kit_for_prompt` → `enrich_plan_metadata_with_registry_v2` → `resolve_scaffold_context`; playbook context appended only when `resolved.source == "v2"` and context is non-empty. Digest verification remains over the original/effective preview prompt; enrichment applies only to the runner prompt.

---

## 4. Chat UX cleanup summary

Implemented per [CODING_PLAN_CARD_REPLACEMENT_PLAN.md](./CODING_PLAN_CARD_REPLACEMENT_PLAN.md) Option C/B (smallest safe step):

| Change | Detail |
|--------|--------|
| **Minimal build-ready surface** | `CodingPlanCard` now shows "Ready to build" + "HAM prepared a safe build preview. Review and approve when you're ready." instead of provider-plan dashboard framing |
| **Provider candidate rows** | Removed/collapsed — no `candidate-row`, provider badges, or alternative list |
| **"Why this plan?" presentation** | Removed/collapsed — no `alternatives-toggle` or `alternatives` drawer |
| **Recommendation reason drawer** | Removed/collapsed — no `recommendation-reason` in normal rendering |
| **Disabled placeholder launch button** | Removed — no `launch-cta-disabled` or `no-launch-footer` |
| **Managed approval panels** | **Preserved** — `ManagedBuildApprovalPanel` and `ManagedOpencodeBuildApprovalPanel` still mount when applicable |
| **OpenCode prefer affordance** | Preserved — optional "Try with OpenCode" CTA when OpenCode is an available alternative |

Source: `frontend/src/features/hermes-workspace/screens/chat/coding-plan/CodingPlanCard.tsx`, mounted in `WorkspaceChatScreen.tsx` (`data-hww-coding-plan-card-wrap`).

---

## 5. Mechanics preserved

These required mechanics were **not** changed in the chat UX cleanup:

- **`ManagedProviderBuildApprovalPanel`** — generic preview/approve/launch/poll engine
- **Droid wrapper** — `ManagedBuildApprovalPanel` (`src/api/droid_build.py` endpoints)
- **OpenCode wrapper** — `ManagedOpencodeBuildApprovalPanel` (`src/api/opencode_build.py` endpoints)
- **preview → approve checkbox → digest-verified launch** — `idle → previewing → previewed → launching → running → succeeded/failed` state machine
- **`confirmed: true` approval gate** — launch only callable from `previewed` + `approved`
- **proposal digest / base revision validation** — `proposal_digest` + `base_revision` from preview passed unchanged into launch (server verifies digest)
- **launch polling** — `running` phase polls `fetchControlPlaneRun(hamRunId)` until terminal status
- **retry / failure handling** — failure phase with `startOver` reset; `SmokePreflightError` surfacing
- **success summary / result wiring** — `SuccessSummary` (`preview_url`, `changed_paths_count`, `snapshot_id`, neutral outcome, technical-details `<details>`)

---

## 6. What remains invisible

Normal users and normal API consumers must **not** see:

- Recipe IDs (e.g. `site.landing-page-core`, `site.dashboard-ui-core`, `game.idle-incremental`)
- Pack IDs (e.g. `pack.site`, `pack.game`)
- `registry_v2_app_type`
- `fallback_reason`
- Gate reports / gate review language
- Scaffold quality issue codes (e.g. `dashboard_`, `city_`, `tactics_`, `landing_` prefixes)
- YAML paths / module names
- Render lengths / render budgets
- Playbook headers (e.g. `Build Registry v2 playbook context:`)
- Provider-echoed Build Registry internals (sanitized from Cursor mission feeds, public mission payloads, launch/status summaries, and projected provider conversation)

Client-supplied `registry_v2_app_type` on launch bodies is **ignored or rejected** for routing; server-side selection follows prompt intent only.

---

## 7. Product UX result

- **Chat is cleaner and less provider/router-like** — users no longer see candidate rows, "Why this plan?", recommendation reasons, or provider-plan framing in the normal `CodingPlanCard` surface.
- **Build kits are backstage** — v2 playbook context improves runner prompts internally; users see outcome-focused language ("Ready to build", "Review and approve when you're ready").
- **Approvals remain safe** — managed approval panels still require preview → checkbox → digest-verified launch; no shortcut around the approval gate.
- **Right pane remains preferred long-term** — preview, status, and result should eventually move to the workbench right pane; chat stays conversational with a short nudge only.

---

## 8. Deferred follow-ups

| Item | Posture |
|------|---------|
| **Move approval/status fully to right pane** | Long-term target per replacement plan Option A; requires dedicated plan before implementation |
| **Provider-label polish inside approval panels** | Lane labels (e.g. "Managed workspace build", "OpenCode build") remain in panel copy; deferred as non-build-kit leakage |
| **Optional debug/operator-only diagnostics** | Candidate/reason details behind explicit operator/debug surface (Option D); not default-on |
| **Conductor preview** | Do not touch unless a new readiness review finds a safe internal seam; recommender, no runner prompt, high leakage risk |
| **Builder Studio task-launch surface** | Must not become a launch entry point; remains config-only |

---

## 9. Tests / validation summary

| Layer | Coverage |
|-------|----------|
| **OpenCode launch seam** | `tests/test_opencode_build_api.py` — flag off/on, internal selection, digest integrity, sanitization |
| **Droid launch seam** | `tests/test_droid_build_api.py` — same pattern + digest integrity |
| **Claude launch seam** | `tests/test_claude_agent_build_api.py` — same pattern + digest integrity |
| **Cursor launch seam** | `tests/test_cursor_agent_workflow.py` — enrichment, digest integrity, launch sanitization |
| **Cursor feed/projection** | `tests/test_cursor_provider_adapter.py`, `tests/test_managed_mission.py` — v2 token redaction in conversation and public payloads |
| **No-exposure guardrails** | `290bf883` — backend conductor/droid/opencode preview + frontend `CodingPlanCard` / `WorkspaceWorkbench` leakage tests |
| **CodingPlanCard frontend** | `frontend/.../coding-plan/__tests__/CodingPlanCard.test.tsx` — minimal ready copy, no candidate/alternatives/placeholder, managed panels when applicable |
| **Approval panel frontend** | `frontend/.../coding-plan/__tests__/ManagedBuildApprovalPanel.test.tsx` — preview/approve/launch flow, digest pass-through, success summary |
| **Chat UX cleanup** | No backend/API/routing/build-registry changes — frontend-only presentation simplification |

---

## 10. Recommended next options

**Invisible orchestration + chat UX cleanup are complete.** Do not reopen provider seams or further strip `CodingPlanCard` without new evidence.

| Option | Description | Posture |
|--------|-------------|---------|
| **A. Pause this workstream** | All provider launch seams and Option C/B chat cleanup are done | **Recommended** |
| **B. Plan right-pane approval/status relocation** | Dedicated plan for Option A from replacement plan; move `ManagedProviderBuildApprovalPanel` to workbench right pane | Next implementation only after dedicated plan |
| **C. Return to product UX work** | Conversation-first flow, right-pane preview/results, slim approval UX | Can run in parallel with Option B planning |
| **D. Resume build-kit recipe expansion** | Per [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md) | Separate strategic decision; requires new readiness review |

**Recommendation:**

- **Pause implementation here** — provider orchestration and chat UX cleanup are complete.
- **Next implementation should be right-pane approval/status relocation only after a dedicated plan** — do not relocate panels without a scoped plan and test expectations.
- **Do not touch conductor preview** — remains deferred.
- **Do not enable Build Registry v2 by default** — opt-in flag preserved.

---

## 11. Non-goals

This checkpoint does **not** authorize:

- New implementation from this document alone
- Recipe or routing YAML changes
- Frontend or Builder Studio changes beyond what is already shipped
- CI workflow changes
- Template or v1 Builder Kit JSON changes
- Default Build Registry v2 enablement
- Surfacing build-kit internals to normal users
- Changes to the coding conductor (remains deferred)
- Builder Studio task-launch surfacing

---

## 12. References

| Document | Role |
|----------|------|
| [INVISIBLE_ORCHESTRATION_PHASE_1_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_PHASE_1_CHECKPOINT.md) | Phase 1 completion: OpenCode launch invisible orchestration |
| [INVISIBLE_ORCHESTRATION_PHASE_2_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_PHASE_2_CHECKPOINT.md) | Phase 2 completion: Droid launch invisible orchestration |
| [INVISIBLE_ORCHESTRATION_PHASE_3_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_PHASE_3_CHECKPOINT.md) | Phase 3 completion: Claude + Cursor launch invisible orchestration |
| [CODING_PLAN_CARD_REPLACEMENT_PLAN.md](./CODING_PLAN_CARD_REPLACEMENT_PLAN.md) | Plan for CodingPlanCard replacement; Option C/B implemented at `ddc2da9b` |
| [INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md](./INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md) | Product/UX posture — conversation-first, invisible kits |
| [INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md](./INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md) | Minimal phased implementation plan (Phase 1–5) |
| [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md) | Strategic next-wave framing |
| [STATUS.md](./STATUS.md) | Live Build Registry v2 status and handoff |

**Implementation touchpoints (already shipped):**

- Provider seams: `src/api/opencode_build.py`, `src/api/droid_build.py`, `src/api/claude_agent_build.py`, `src/ham/cursor_agent_workflow.py`, `src/ham/cursor_provider_adapter.py`, `src/api/cursor_managed_missions.py`
- Chat UX: `frontend/src/features/hermes-workspace/screens/chat/coding-plan/CodingPlanCard.tsx`, `ManagedProviderBuildApprovalPanel.tsx`, `ManagedBuildApprovalPanel.tsx`, `ManagedOpencodeBuildApprovalPanel.tsx`
