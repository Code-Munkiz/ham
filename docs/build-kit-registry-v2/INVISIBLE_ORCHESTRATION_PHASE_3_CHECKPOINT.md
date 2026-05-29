# Invisible Orchestration Phase 3 Checkpoint

Closeout checkpoint after **Phase 3** of invisible Build Kit orchestration landed on `origin/main`. This document records what shipped in the third backend/internal-only seams — **Claude Code / Claude Agent launch** and **Cursor launch** (including Cursor mission-feed/public-payload sanitization) — and confirms that coding conductor preview and `CodingPlanCard` UX cleanup remain separate work. This checkpoint is **not** approval for new recipes, routing, templates, runtime default v2 enablement, frontend changes, Builder Studio surfacing, or further orchestration expansion without explicit review. Build-kit internals remain invisible to normal users. For live registry status see [STATUS.md](STATUS.md).

**Baseline:** `origin/main` at `ed46a156` — `feat(builder): apply invisible orchestration to cursor launch`.

**Claude seam:** `b54de596` — `feat(builder): apply invisible orchestration to claude launch`.

**Phase 2 baseline:** `52774a89` — `feat(builder): apply invisible orchestration to droid launch`.

**Phase 1 baseline:** `a7cc1c4e` — `feat(builder): apply invisible orchestration to opencode launch`.

**Prior guardrails:** `290bf883` — `test(builder): guard against build kit internals exposure`.

---

## 1. Executive summary

**Phase 3 is complete.**

- **Cursor launch** now applies Build Registry v2 playbook context **internally** when `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy and v2 resolves for the user prompt.
- **Claude Code / Claude Agent launch** (Phase 3a) applies the same internal enrichment pattern on its managed-workspace launch path.
- **OpenCode, Droid, Claude, and Cursor launch seams are now complete** — all four provider launch paths enrich runner prompts internally without exposing build-kit internals to normal users.
- **Normal users do not see build-kit internals** — recipe IDs, pack IDs, routing metadata, gate language, YAML paths, render budgets, playbook headers, and provider-echoed registry copy stay out of normal API payloads, mission feeds, summaries, and UI copy.
- **This checkpoint adds no code, routing, recipes, templates, or runtime changes** — documentation only.

---

## 2. Current baseline

| Field | Value |
|-------|--------|
| **Latest pushed commit** | `ed46a156` — `feat(builder): apply invisible orchestration to cursor launch` |
| **Phase 1 OpenCode seam** | Complete on `origin/main` at `a7cc1c4e` |
| **Phase 2 Droid seam** | Complete on `origin/main` at `52774a89` |
| **Phase 3 Claude seam** | Complete on `origin/main` at `b54de596` |
| **Phase 3 Cursor seam** | Complete on `origin/main` at `ed46a156` |
| **Build-kit guardrails on `origin/main`** | `290bf883` — backend conductor/droid/opencode preview + frontend `CodingPlanCard` / `WorkspaceWorkbench` leakage tests |
| **v2 opt-in** | **`HAM_BUILD_REGISTRY_V2_ENABLED`** must be truthy for internal v2 playbook context on launch paths |
| **v1 default** | Preserved — flag off, no resolved app type, or v2 resolution failure leaves original prompt unchanged |
| **Conversation-first UX** | Preserved — users still plan/approve/launch through chat; no kit picker, catalog, or routing narration |
| **Builder Studio** | Remains non-surfaced / config-only |

---

## 3. What Phase 3 implemented

Phase 3 delivered **tiny internal helper seams** on Claude and Cursor launch paths, mirroring OpenCode and Droid, plus **Cursor-specific feed/payload sanitization** because provider conversation is projected back into HAM mission feeds.

### Claude Code / Claude Agent launch

| Step | Mechanism | Location |
|------|-----------|----------|
| Template kind | `select_kit_for_prompt(user_prompt)` | `src/api/claude_agent_build.py` (via internal helper) |
| Metadata enrichment | `enrich_plan_metadata_with_registry_v2({...}, user_prompt)` | `src/ham/build_registry/intent.py` (called from Claude helper) |
| Context resolution | `resolve_scaffold_context(metadata=..., template_kind=...)` | `src/ham/build_registry/scaffold_context.py` (called from Claude helper) |
| Runner prompt | Playbook header + context appended **only** when `resolved.source == "v2"` and context is non-empty | `_enrich_internal_launch_prompt(...)` → `run_claude_agent_mission(user_prompt=enriched_prompt, ...)` |
| Application point | Applied **after** digest verification (`verify_claude_agent_launch_against_preview`) and **before** `run_claude_agent_mission` | `src/api/claude_agent_build.py` — `launch_claude_agent_build` |
| Normal payload hygiene | `_sanitize_normal_user_copy(...)` on launch `summary` and `error_summary` | `src/api/claude_agent_build.py` response assembly |

### Cursor launch + mission-feed/public-payload sanitization

| Step | Mechanism | Location |
|------|-----------|----------|
| Template kind | `select_kit_for_prompt(task_prompt)` | `src/ham/cursor_agent_workflow.py` (via internal helper) |
| Metadata enrichment | `enrich_plan_metadata_with_registry_v2({...}, user_prompt)` | `src/ham/build_registry/intent.py` (called from Cursor helper) |
| Context resolution | `resolve_scaffold_context(metadata=..., template_kind=...)` | `src/ham/build_registry/scaffold_context.py` (called from Cursor helper) |
| Runner prompt | Playbook context appended **only** when v2 resolves; effective launch prompt rebuilt when enrichment changes the task text | `_enrich_internal_launch_prompt(...)` → `cursor_api_launch_agent(prompt_text=launch_prompt_text, ...)` |
| Application point | Applied **after** digest inputs are finalized/verified (digest still computed over original/effective preview prompt) and **before** `cursor_api_launch_agent` | `src/ham/cursor_agent_workflow.py` — `run_cursor_agent_launch` |
| Launch/status payload hygiene | `_sanitize_normal_user_copy(...)` on launch/status summaries and errors | `src/ham/cursor_agent_workflow.py` — `summarize_cursor_agent_payload`, launch/status error paths |
| Provider feed projection hygiene | Sanitize projected conversation and SDK-bridge event messages | `src/ham/cursor_provider_adapter.py` — `map_cursor_conversation_to_feed_events`, `map_cursor_sdk_bridge_to_feed_events` |
| Public mission/feed boundary hygiene | Sanitize feed rows, public mission title/summary/error fields, checkpoint reasons, control-plane public subset | `src/api/cursor_managed_missions.py` — `_mission_feed_row_from_event`, `_public_mission`, `_control_plane_public_subset` |

**Important:** Preview/digest contracts are unchanged on all launch paths. Enrichment affects the **runner prompt** passed to the provider, not the shape of normal preview or launch JSON returned to the browser. Client-supplied `registry_v2_app_type` is not honored for routing; server-side selection follows prompt intent only.

**Explicitly unchanged in Phase 3:**

- No frontend UI behavior changes
- No coding conductor preview changes
- No `CodingPlanCard` changes
- No Builder Studio surfacing

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
- Provider-echoed Build Registry internals (sanitized from Cursor mission feeds, public mission payloads, launch/status summaries, and projected provider conversation)

Client-supplied `registry_v2_app_type` on launch bodies is **ignored or rejected** for routing; server-side selection follows prompt intent only.

---

## 5. Tests and guarantees

| Layer | Coverage | Commit / files |
|-------|----------|----------------|
| **Backend preview guardrails** | Normal conductor/droid/opencode preview payloads must not contain forbidden build-registry tokens | `290bf883` — `tests/test_coding_conductor_api.py`, `tests/test_droid_build_api.py`, `tests/test_opencode_build_api.py` |
| **Frontend guardrails** | `CodingPlanCard` and `WorkspaceWorkbench` visible copy must not show forbidden tokens | `290bf883` — `frontend/src/features/hermes-workspace/.../__tests__/` |
| **OpenCode launch seam (Phase 1)** | Flag off → no v2 context; flag on + landing/dashboard prompts → internal selection; client app-type override ignored; leaky runner summary sanitized | `a7cc1c4e` — `tests/test_opencode_build_api.py` |
| **Droid launch seam (Phase 2)** | Same pattern + digest integrity after enrichment | `52774a89` — `tests/test_droid_build_api.py` |
| **Claude launch seam (Phase 3)** | Flag off → no v2 context; flag on + landing/dashboard prompts → internal selection; digest integrity; client app-type override rejected; leaky runner summary/error sanitized | `b54de596` — `tests/test_claude_agent_build_api.py` |
| **Cursor launch seam (Phase 3)** | Flag off → no v2 context; flag on + landing/dashboard prompts → internal selection; digest integrity; fake `registry_v2_app_type` text does not control routing; leaky launch summary sanitized | `ed46a156` — `tests/test_cursor_agent_workflow.py` |
| **Cursor feed/projection sanitization (Phase 3)** | Provider conversation and SDK-bridge projections redact forbidden v2 tokens before feed events | `ed46a156` — `tests/test_cursor_provider_adapter.py` |
| **Managed mission public payload (Phase 3)** | Mission feed and public mission payloads do not leak forbidden v2 tokens | `ed46a156` — `tests/test_managed_mission.py` |

**Claude launch tests added in Phase 3:**

- `test_internal_launch_prompt_enrichment_flag_off_no_v2_context`
- `test_internal_launch_prompt_enrichment_flag_on_landing_selects_site_landing_page_core`
- `test_internal_launch_prompt_enrichment_flag_on_dashboard_selects_site_dashboard_ui_core`
- `test_launch_digest_integrity_with_internal_landing_enrichment`
- `test_launch_digest_integrity_with_internal_dashboard_enrichment`
- `test_launch_rejects_client_supplied_registry_v2_app_type_field`
- `test_launch_sanitizes_forbidden_build_registry_tokens_in_user_visible_payload`

**Cursor launch and feed tests added in Phase 3:**

- `test_internal_launch_prompt_enrichment_flag_off_no_v2_context`
- `test_internal_launch_prompt_enrichment_flag_on_landing_selects_site_landing_page_core`
- `test_internal_launch_prompt_enrichment_flag_on_dashboard_selects_site_dashboard_ui_core`
- `test_internal_launch_prompt_ignores_fake_registry_v2_app_type_in_prompt`
- `test_launch_digest_verification_uses_original_effective_prompt_then_launch_enriches`
- `test_launch_sanitizes_forbidden_build_registry_tokens_in_user_visible_payload`
- `test_map_cursor_redacts_build_registry_v2_tokens_in_message`
- `test_map_cursor_sdk_bridge_redacts_build_registry_v2_tokens`
- `test_public_mission_sanitizes_forbidden_build_registry_tokens`

**Guarantees after Phase 3:**

- No frontend UI behavior changes from Phase 1–3 implementation (backend-only).
- Existing scaffold path (`builder_chat_scaffold` → `generate_scaffold` → `resolve_scaffold_context`) unchanged.
- v2 remains opt-in; v1 fallback preserved when flag is off or v2 does not resolve.
- Coding conductor preview remains deferred — not modified in Phase 3.

---

## 6. Provider seam status table

| Provider | Seam status | Exposure guard | Notes |
|----------|-------------|----------------|-------|
| **OpenCode** | Complete (Phase 1) | Launch `summary` / `error_summary` sanitization | `_enrich_internal_launch_prompt` in `src/api/opencode_build.py`; applied before `run_opencode_mission` |
| **Droid / Factory** | Complete (Phase 2) | Launch `summary` / `error_summary` sanitization | `_enrich_internal_launch_prompt` in `src/api/droid_build.py`; applied after digest verification, before `execute_droid_build_workflow`; Droid lane may still be token-gated/inert in production |
| **Claude** | Complete (Phase 3) | Launch `summary` / `error_summary` sanitization | `_enrich_internal_launch_prompt` in `src/api/claude_agent_build.py`; applied after digest verification, before `run_claude_agent_mission` |
| **Cursor** | Complete (Phase 3) | Launch/status summary sanitization **plus** mission-feed/public-payload sanitization | `_enrich_internal_launch_prompt` in `src/ham/cursor_agent_workflow.py`; feed projection in `src/ham/cursor_provider_adapter.py`; public boundary in `src/api/cursor_managed_missions.py`; enrichment after digest verification, before `cursor_api_launch_agent` |

---

## 7. Remaining UX work

**CodingPlanCard cleanup is separate from provider orchestration.**

- All four provider **launch** seams now enrich runner prompts internally. That work does not require or imply changes to the visible chat provider/plan card.
- **`CodingPlanCard` may be removable, hideable, or replaceable**, but only after preserving required approval/digest/launch mechanics currently hosted inside it (e.g. `ManagedProviderBuildApprovalPanel` and related launch controls).
- Product direction prefers a **magical conversation-first flow** — users should not see provider/plan machinery unless necessary for safety.
- Any cleanup should **keep chat clean** and move approval/status toward the **right pane** or a **slim approval UX**, without surfacing build-kit internals.
- **Coding conductor preview remains deferred** — it is a recommender with no runner prompt and higher risk of kit metadata leakage through `CodingPlanCard`; do not wire conductor directly without a separate safe internal-only seam audit.

---

## 8. Recommended next options

**Phase 3 is complete.** OpenCode, Droid, Claude, and Cursor launch seams are shipped. **Do not implement conductor preview directly yet.**

| Option | Description | Posture |
|--------|-------------|---------|
| **A. Create CodingPlanCard replacement/removal plan** | Design how to hide or replace the visible provider/plan card while preserving approval/digest/launch safety | **Recommended next step if continuing this thread** |
| **B. Pause invisible orchestration implementation** | All four provider launch seams are done; return to broader product UX work | Reasonable if product polish is the priority |
| **C. Return to broader product UX work** | Conversation-first flow, right-pane preview/results, slim approval UX | Can run in parallel with option A |
| **D. Resume build-kit recipe expansion** | Define next kit expansion per [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md) | Separate strategic decision; requires new readiness review |

**Recommendation:**

- **Phase 3 is complete** — do not reopen OpenCode, Droid, Claude, or Cursor launch seams without new evidence.
- **Do not implement conductor preview directly yet** — it remains deferred (recommender, no runner prompt, high `CodingPlanCard` leakage risk).
- **If continuing this thread, create a CodingPlanCard replacement/removal plan next** — preserve `ManagedProviderBuildApprovalPanel` approval/digest/launch mechanics; keep chat magical; move status/approval toward right pane or slim UX.
- **Any UX cleanup should be separate from provider orchestration** — one focused plan or tiny PR per UX change, same invisibility rules for any future backend touchpoints.

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
- `CodingPlanCard` removal/replacement implementation (planning only unless explicitly approved)

---

## 10. References

| Document | Role |
|----------|------|
| [INVISIBLE_ORCHESTRATION_PHASE_1_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_PHASE_1_CHECKPOINT.md) | Phase 1 completion: OpenCode launch invisible orchestration |
| [INVISIBLE_ORCHESTRATION_PHASE_2_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_PHASE_2_CHECKPOINT.md) | Phase 2 completion: Droid launch invisible orchestration + Phase 3 audit framing |
| [INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md](./INVISIBLE_ORCHESTRATION_IMPLEMENTATION_PLAN.md) | Minimal phased implementation plan (Phase 1–5) |
| [INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md](./INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md) | Product/UX posture — conversation-first, invisible kits |
| [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md) | Strategic next-wave framing after website-pack foundation |
| [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md) | Website-pack foundation closeout (`site.landing-page-core`, `site.dashboard-ui-core`) |
| [STATUS.md](./STATUS.md) | Live Build Registry v2 status and handoff |

**Implementation touchpoints (Phase 3 only):**

- `src/api/claude_agent_build.py` — `_enrich_internal_launch_prompt`, `_sanitize_normal_user_copy`, `launch_claude_agent_build`
- `src/ham/cursor_agent_workflow.py` — `_enrich_internal_launch_prompt`, `_sanitize_normal_user_copy`, `run_cursor_agent_launch`
- `src/ham/cursor_provider_adapter.py` — feed projection sanitization for conversation and SDK-bridge events
- `src/api/cursor_managed_missions.py` — public mission/feed/control-plane payload sanitization
- `tests/test_claude_agent_build_api.py` — Claude internal enrichment and launch sanitization tests
- `tests/test_cursor_agent_workflow.py` — Cursor internal enrichment, digest integrity, and launch sanitization tests
- `tests/test_cursor_provider_adapter.py` — Cursor feed projection sanitization tests
- `tests/test_managed_mission.py` — managed mission public payload and feed sanitization tests
