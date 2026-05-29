# Invisible Orchestration Phase 2 Checkpoint

Closeout checkpoint after **Phase 2** of invisible Build Kit orchestration landed on `origin/main`. This document records what shipped in the second backend/internal-only seam — **Droid launch** — and confirms the deferral of coding conductor preview. This checkpoint is **not** approval for new recipes, routing, templates, runtime default v2 enablement, frontend changes, Builder Studio surfacing, or further orchestration expansion without explicit review. Build-kit internals remain invisible to normal users. For live registry status see [STATUS.md](STATUS.md).

**Baseline:** `origin/main` at `52774a89` — `feat(builder): apply invisible orchestration to droid launch`.

**Phase 1 baseline:** `a7cc1c4e` — `feat(builder): apply invisible orchestration to opencode launch`.

**Prior guardrails:** `290bf883` — `test(builder): guard against build kit internals exposure`.

---

## 1. Executive summary

**Phase 2 is complete.**

- **Droid launch** now applies Build Registry v2 playbook context **internally** when `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy and v2 resolves for the user prompt.
- Both **OpenCode launch (Phase 1)** and **Droid launch (Phase 2)** now have invisible orchestration seams, enriching their respective runner prompts internally.
- **Normal users do not see build-kit internals** — recipe IDs, pack IDs, routing metadata, gate language, YAML paths, render budgets, and playbook headers stay out of normal API payloads and UI copy.
- **This checkpoint adds no code, routing, recipes, templates, or runtime changes** — documentation only.

---

## 2. Current baseline

| Field | Value |
|-------|--------|
| **Latest pushed commit** | `52774a89` — `feat(builder): apply invisible orchestration to droid launch` |
| **Phase 1 OpenCode seam** | Complete on `origin/main` at `a7cc1c4e` |
| **Phase 2 Droid seam** | Complete on `origin/main` at `52774a89` |
| **Build-kit guardrails on `origin/main`** | `290bf883` — backend conductor/droid/opencode preview + frontend `CodingPlanCard` / `WorkspaceWorkbench` leakage tests |
| **v2 opt-in** | **`HAM_BUILD_REGISTRY_V2_ENABLED`** must be truthy for internal v2 playbook context on launch paths |
| **v1 default** | Preserved — flag off, no resolved app type, or v2 resolution failure leaves original prompt unchanged |
| **Conversation-first UX** | Preserved — users still plan/approve/launch through chat; no kit picker, catalog, or routing narration |
| **Builder Studio** | Remains non-surfaced / config-only |

---

## 3. What Phase 2 implemented

Phase 2 delivered a **tiny internal helper seam** on the Droid managed-workspace launch path only, mirroring OpenCode:

| Step | Mechanism | Location |
|------|-----------|----------|
| Template kind | `select_kit_for_prompt(user_prompt)` | `src/api/droid_build.py` (via internal helper) |
| Metadata enrichment | `enrich_plan_metadata_with_registry_v2({...}, user_prompt)` | `src/ham/build_registry/intent.py` (called from Droid helper) |
| Context resolution | `resolve_scaffold_context(metadata=..., template_kind=...)` | `src/ham/build_registry/scaffold_context.py` (called from Droid helper) |
| Runner prompt | Playbook header + context appended **only** when `resolved.source == "v2"` and context is non-empty | `_enrich_internal_launch_prompt(...)` → `execute_droid_build_workflow(user_prompt=enriched_prompt, ...)` |
| Application point | Applied **after** digest verification (`verify_launch_against_preview`) and **before** `execute_droid_build_workflow` | `src/api/droid_build.py` — `launch_droid_build` |
| Normal payload hygiene | `_sanitize_normal_user_copy(...)` on launch `summary` and `error_summary` | `src/api/droid_build.py` response assembly |

**Important:** Preview/digest contracts are unchanged. Enrichment affects the **runner prompt** passed to Droid, not the shape of normal preview or launch JSON returned to the browser. Client-supplied `registry_v2_app_type` is rejected (`422`) via `extra="forbid"` on `DroidBuildLaunchBody` and tested behavior.

---

## 4. What stayed invisible

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
- Client app-type override behavior — server-side selection follows prompt intent only

---

## 5. Tests and guarantees

| Layer | Coverage | Commit / files |
|-------|----------|----------------|
| **Backend preview guardrails** | Normal conductor/droid/opencode preview payloads must not contain forbidden build-registry tokens | `290bf883` — `tests/test_coding_conductor_api.py`, `tests/test_droid_build_api.py`, `tests/test_opencode_build_api.py` |
| **Frontend guardrails** | `CodingPlanCard` and `WorkspaceWorkbench` visible copy must not show forbidden tokens | `290bf883` — `frontend/src/features/hermes-workspace/.../__tests__/` |
| **OpenCode launch seam (Phase 1 pattern)** | Flag off → no v2 context; flag on + landing/dashboard prompts → internal `site.landing-page-core` / `site.dashboard-ui-core` selection; client app-type override ignored; leaky runner summary sanitized | `a7cc1c4e` — `tests/test_opencode_build_api.py` |
| **Droid launch seam (Phase 2)** | Flag off → no v2 context; flag on + landing/dashboard prompts → internal selection; digest integrity preserved after enrichment; client app-type override rejected; leaky runner summary/error sanitized | `52774a89` — `tests/test_droid_build_api.py` |

**Droid launch tests added in Phase 2:**

- `test_internal_launch_prompt_enrichment_flag_off_no_v2_context`
- `test_internal_launch_prompt_enrichment_flag_on_landing_selects_site_landing_page_core`
- `test_internal_launch_prompt_enrichment_flag_on_dashboard_selects_site_dashboard_ui_core`
- `test_launch_digest_integrity_with_internal_landing_enrichment`
- `test_launch_digest_integrity_with_internal_dashboard_enrichment`
- `test_launch_rejects_client_supplied_registry_v2_app_type_field`
- `test_launch_sanitizes_forbidden_build_registry_tokens_in_user_visible_payload`

**Guarantees after Phase 2:**

- No frontend UI behavior changes from Phase 1 or 2 implementation (backend-only).
- Existing scaffold path (`builder_chat_scaffold` → `generate_scaffold` → `resolve_scaffold_context`) unchanged.
- v2 remains opt-in; v1 fallback preserved when flag is off or v2 does not resolve.

---

## 6. Scope boundaries

| In scope (Phase 1 & 2) | Out of scope (deferred) |
|------------------------|-------------------------|
| OpenCode **launch** runner-prompt enrichment | Coding conductor preview/planning metadata bridge |
| Droid **launch** runner-prompt enrichment | Default v2 enablement |
| Internal-only metadata + context resolution | Builder Studio task-launch surface |
| Launch response summary/error sanitization | User-visible kit catalog or routing narration |
| Tests for OpenCode & Droid seams + guardrails | Droid lane currently token-gated/inert in production; seam is ready for future live enablement |

**Product posture unchanged:** build initiation stays in chat; Settings → Builders remains config-only; Builder Studio is not a primary execution surface.

---

## 7. Why conductor preview remains deferred

The coding conductor preview (`src/api/coding_conductor.py`) remains intentionally deferred because:

- **Conductor preview is a recommender, not a builder** — it classifies user intent and suggests provider candidates but does not execute a build or pass a prompt to a runner that consumes playbook context.
- **No runner prompt seam** — unlike OpenCode and Droid launch, there is no internal runner prompt to enrich within the conductor flow.
- **Response is rendered directly by `CodingPlanCard`** — conductor output (candidates, recommendation reasons, blockers) is consumed and displayed in the chat UI. Adding internal metadata to the API response risks surfacing kit details through visible copy.
- **Higher risk of leaking kit metadata** — any route/kit/fallback fields added to preview payloads could appear in `CodingPlanCard` without a safe sanitization boundary.
- **Any future work requires a separate readiness/seam review** — conductor integration is not an automatic Phase 3; it needs its own audit before implementation.

---

## 8. Recommended next options

**Phase 2 is complete.** OpenCode and Droid launch seams are shipped. **Do not implement conductor preview directly yet** — it remains deferred until a later audit identifies a safe internal-only seam.

**Next step: read-only Phase 3 seam audit** (no implementation from this checkpoint). Audit scope:

| Audit target | Why audit now |
|--------------|---------------|
| **Cursor launch/build seam** | OpenCode and Droid are done; Cursor orchestration status is not yet proven |
| **Claude Code launch/build seam** | Same — Claude lane status is not yet proven |
| **`CodingPlanCard` UX** | Product direction prefers a magical conversation-first flow; the visible provider/plan card may need to be removed, hidden, or replaced |

**Phase 3 audit questions (read-only):**

- Does Cursor have a safe runner-prompt seam analogous to OpenCode/Droid launch?
- Does Claude Code have a safe runner-prompt seam analogous to OpenCode/Droid launch?
- Can `CodingPlanCard` be removed, hidden, or replaced without breaking approval/launch safety?
- Does conductor preview expose kit metadata through `CodingPlanCard`, and is there any internal-only path that avoids that leakage?

**After the audit:**

| Option | Description | Posture |
|--------|-------------|---------|
| **A. Read-only Phase 3 seam audit** | Cursor + Claude + `CodingPlanCard` review before any new implementation | **Recommended next step** |
| **B. Tiny implementation PR(s)** | Apply invisible orchestration to a proven Cursor or Claude seam, or adjust `CodingPlanCard` visibility — **only after** the audit identifies a safe target | Separate tiny PR per target |
| **C. Add broader no-exposure tests if needed** | Broaden guardrails to other potential leak surfaces (e.g. persisted control-plane summaries) | Low risk; test-only, can run in parallel with audit |
| **D. Resume build-kit expansion** | Define next kit expansion per [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md) | Separate strategic decision |

**Recommendation:**

- **Phase 2 is complete** — do not reopen OpenCode or Droid seams without new evidence.
- **Do not implement conductor preview directly yet** — it is a recommender with no runner prompt and high `CodingPlanCard` leakage risk.
- **Run the read-only Phase 3 seam audit next** covering Cursor launch/build, Claude Code launch/build, and whether `CodingPlanCard` can be removed, hidden, or replaced.
- **Any implementation after that audit should be separate and tiny** — one proven seam or UX change per PR, same invisibility rules, same opt-in flag, same no-exposure tests.
- **Conductor preview remains deferred** unless a later audit identifies a safe internal-only seam that does not surface kit metadata through normal UI copy.

---

## 9. Non-goals

This checkpoint does **not** authorize:

- New implementation from this document alone
- Recipe or routing YAML changes
- Frontend or Builder Studio changes
- CI workflow changes
- Template or v1 Builder Kit JSON changes
- Default Build Registry v2 enablement
- Surfacing build-kit internals to normal users
- Changes to the coding conductor (remains deferred)

---

## 10. References

| Document | Role |
|----------|------|
| [INVISIBLE_ORCHESTRATION_PHASE_1_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_PHASE_1_CHECKPOINT.md) | Phase 1 completion: OpenCode launch invisible orchestration |
| [INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md](./INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md) | Minimal phased implementation plan (Phase 1–5) |
| [INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md](./INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md) | Product/UX posture — conversation-first, invisible kits |
| [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md) | Strategic next-wave framing after website-pack foundation |
| [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md) | Website-pack foundation closeout (`site.landing-page-core`, `site.dashboard-ui-core`) |
| [STATUS.md](./STATUS.md) | Live Build Registry v2 status and handoff |

**Implementation touchpoints (Phase 2 only):**

- `src/api/droid_build.py` — `_enrich_internal_launch_prompt`, `_sanitize_normal_user_copy`, `launch_droid_build`
- `tests/test_droid_build_api.py` — internal enrichment and launch sanitization tests
