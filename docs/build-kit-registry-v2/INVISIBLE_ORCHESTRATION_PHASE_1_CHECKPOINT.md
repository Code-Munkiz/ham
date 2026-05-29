# Invisible Orchestration Phase 1 Checkpoint

Closeout checkpoint after **Phase 1** of invisible Build Kit orchestration landed on `origin/main`. This document records what shipped in the first backend/internal-only seam — **OpenCode launch** — and is **not** approval for new recipes, routing, templates, runtime default v2 enablement, frontend changes, Builder Studio surfacing, or further orchestration expansion. Build-kit internals remain invisible to normal users. For live registry status see [STATUS.md](STATUS.md).

**Baseline:** `origin/main` at `a7cc1c4e` — `feat(builder): apply invisible orchestration to opencode launch`.

**Prior guardrails:** `290bf883` — `test(builder): guard against build kit internals exposure`.

---

## 1. Executive summary

**Phase 1 is complete.**

- **OpenCode launch** now applies Build Registry v2 playbook context **internally** when `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy and v2 resolves for the user prompt.
- **Normal users do not see build-kit internals** — recipe IDs, pack IDs, routing metadata, gate language, YAML paths, render budgets, and playbook headers stay out of normal API payloads and UI copy.
- **This checkpoint adds no code, routing, recipes, templates, or runtime changes** — documentation only.

---

## 2. Current baseline

| Field | Value |
|-------|--------|
| **Latest pushed commit** | `a7cc1c4e` — `feat(builder): apply invisible orchestration to opencode launch` |
| **Exposure guardrails on `origin/main`** | `290bf883` — backend conductor/droid/opencode preview guardrails + frontend `CodingPlanCard` / `WorkspaceWorkbench` leakage tests |
| **OpenCode launch seam on `origin/main`** | `src/api/opencode_build.py` — `_enrich_internal_launch_prompt(...)` applied in `_run_opencode_launch_core(...)` before `run_opencode_mission(...)` |
| **v2 opt-in** | **`HAM_BUILD_REGISTRY_V2_ENABLED`** must be truthy for internal v2 playbook context on the launch path |
| **v1 default** | Preserved — flag off, no resolved app type, or v2 resolution failure leaves the original user prompt unchanged for the runner |
| **Conversation-first UX** | Preserved — users still plan/approve/launch through chat; no kit picker, catalog, or routing narration |

---

## 3. What Phase 1 implemented

Phase 1 delivered a **tiny internal helper seam** (Option B) on the OpenCode managed-workspace launch path only:

| Step | Mechanism | Location |
|------|-----------|----------|
| Template kind | `select_kit_for_prompt(user_prompt)` | `src/api/opencode_build.py` |
| Metadata enrichment | `enrich_plan_metadata_with_registry_v2({...}, user_prompt)` | `src/ham/build_registry/intent.py` (called from launch helper) |
| Context resolution | `resolve_scaffold_context(metadata=..., template_kind=...)` | `src/ham/build_registry/scaffold_context.py` (called from launch helper) |
| Runner prompt | Playbook header + context appended **only** when `resolved.source == "v2"` and context is non-empty | `_enrich_internal_launch_prompt(...)` → `run_opencode_mission(user_prompt=enriched_prompt, ...)` |
| Normal payload hygiene | `_sanitize_normal_user_copy(...)` on launch `summary` and `error_summary` | `_run_opencode_launch_core(...)` response assembly |

**Important:** Preview/digest contracts are unchanged. Enrichment affects the **runner prompt** passed to OpenCode, not the shape of normal preview or launch JSON returned to the browser.

---

## 4. What stayed invisible

Normal users and normal API consumers must **not** see:

- Recipe IDs (e.g. `site.landing-page-core`, `site.dashboard-ui-core`)
- Pack IDs (e.g. `pack.site`, `pack.game`)
- `registry_v2_app_type`
- `fallback_reason`
- Gate reports / gate review language
- Scaffold quality issue codes (e.g. `dashboard_`, `city_`, `tactics_`, `landing_` prefixes)
- YAML paths / module names
- Render lengths / render budgets
- Playbook headers (e.g. `Build Registry v2 playbook context:`)

Client-supplied `registry_v2_app_type` on launch bodies is **ignored** for routing; server-side selection follows prompt intent only.

---

## 5. Tests and guarantees

| Layer | Coverage | Commit / files |
|-------|----------|----------------|
| **Backend preview guardrails** | Normal conductor preview payloads must not contain forbidden build-registry tokens | `290bf883` — `tests/test_coding_conductor_api.py` |
| **Backend build preview guardrails** | Normal Droid/OpenCode **preview** responses must not leak internals | `290bf883` — `tests/test_droid_build_api.py`, `tests/test_opencode_build_api.py` |
| **Frontend guardrails** | `CodingPlanCard` and `WorkspaceWorkbench` visible copy must not show forbidden tokens | `290bf883` — `frontend/src/features/hermes-workspace/.../__tests__/` |
| **OpenCode launch seam** | Flag off → no v2 context appended; flag on + landing/dashboard prompts → internal `site.landing-page-core` / `site.dashboard-ui-core` selection; client app-type override ignored; leaky runner summary sanitized in normal launch payload | `a7cc1c4e` — `tests/test_opencode_build_api.py` |

**Guarantees after Phase 1:**

- No frontend UI behavior changes from Phase 1 implementation (backend-only).
- Existing scaffold path (`builder_chat_scaffold` → `generate_scaffold` → `resolve_scaffold_context`) unchanged; Phase 1 did not broaden scaffold behavior beyond the OpenCode launch seam.
- v2 remains opt-in; v1 fallback preserved when flag is off or v2 does not resolve.

---

## 6. Scope boundaries

| In scope (Phase 1) | Out of scope (deferred) |
|--------------------|-------------------------|
| OpenCode **launch** runner-prompt enrichment | Droid launch orchestration |
| Internal-only metadata + context resolution | Conductor/build preview planning metadata bridge |
| Launch response summary/error sanitization | Default v2 enablement |
| Tests for the OpenCode seam + prior guardrails | Builder Studio task-launch surface |
| | User-visible kit catalog or routing narration |

**Product posture unchanged:** build initiation stays in chat; Settings → Builders remains config-only; Builder Studio is not a primary execution surface.

---

## 7. Recommended next options

| Option | Description | Posture |
|--------|-------------|---------|
| **A. Extend invisible orchestration to Droid launch** | Mirror the OpenCode internal prompt enrichment pattern on `src/api/droid_build.py` launch path if a safe seam exists | Separate tiny PR after seam audit |
| **B. Extend conductor/build preview planning** | Internal-only metadata for coding conductor / provider preview lanes without changing normal payload shape | Separate tiny PR; do not expose metadata to frontend |
| **C. Add more no-exposure regression tests** | Broaden guardrails as new seams land (launch payloads, persisted control-plane summaries) | Low risk; keep test-only unless a leak is found |
| **D. Pause implementation** | Return to conversation-first product UX work; kits already improve scaffold + OpenCode launch when opt-in | Reasonable if product polish is the priority |

**Recommendation:**

- **Do not expand immediately** without a small seam audit for the next target (Droid vs conductor vs other launch proxies).
- **If continuing orchestration**, treat **Droid launch** and **conductor/preview planning** as **separate tiny PRs** — same invisibility rules, same opt-in flag, same no-exposure tests.

---

## 8. Non-goals

This checkpoint does **not** authorize:

- New implementation from this document alone
- Recipe or routing YAML changes
- Frontend or Builder Studio changes
- CI workflow changes
- Template or v1 Builder Kit JSON changes
- Default Build Registry v2 enablement
- Surfacing build-kit internals to normal users

---

## 9. References

| Document | Role |
|----------|------|
| [INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md](./INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md) | Product/UX posture — conversation-first, invisible kits |
| [INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md](./INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md) | Minimal phased implementation plan (Phase 1–5) |
| [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md) | Strategic next-wave framing after website-pack foundation |
| [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md) | Website-pack foundation closeout (`site.landing-page-core`, `site.dashboard-ui-core`) |
| [STATUS.md](./STATUS.md) | Live Build Registry v2 status and handoff |

**Implementation touchpoints (Phase 1 only):**

- `src/api/opencode_build.py` — `_enrich_internal_launch_prompt`, `_sanitize_normal_user_copy`, `_run_opencode_launch_core`
- `tests/test_opencode_build_api.py` — internal enrichment and launch sanitization tests
