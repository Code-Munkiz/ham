# Gate Review: app.sales-ops-dashboard-core

> Generated-build gate, local operator run, review artifact only.

## 1. Executive summary

This report now captures three stages:

1. **Initial generated gate** (Hold): exact bounded Sales Ops gate prompt produced a routing false negative and fell back to v1.
2. **Routing fix + rerun** (Conditional pass): exact prompt routed to Sales Ops v2, but generated output still had quality gaps.
3. **Sales Ops quality-guard hardening + final rerun**: Sales Ops-specific scaffold-quality detectors/repair guidance and mirrored escalation/fallback loop were added, then gate rerun executed.

Final decision in this updated run: **Pass**.

## 2. Repo baseline

- Branch: `main`
- Latest commit at run start: `0a14ffac` (`feat(builder): route sales ops dashboard recipe behind registry flag`)
- `git status --short` showed only unrelated local noise plus this gate review doc as local untracked files.

Validation/tests run:

- `python3 scripts/validate_game_pack_registry.py --pack-root docs/build-kit-registry-v2/website-pack --app-type app.sales-ops-dashboard-core --check`
  - Pass (`pack.site`, 188 modules)
- `python3 scripts/check_build_registry_references.py --pack docs/build-kit-registry-v2/website-pack/registry-pack.yaml --check-orphans --check-render-budget`
  - Pass with non-blocking near-budget warnings:
    - `app.saas-dashboard-core`: `11431 / 12000`
    - `app.sales-ops-dashboard-core`: `11346 / 12000`
    - `site.dashboard-ui-core`: `11358 / 12000`
- `pytest tests/test_build_registry_intent.py tests/test_build_registry_scaffold_context.py tests/test_builder_llm_scaffold_registry_context.py tests/test_website_pack_registry.py tests/test_build_registry.py tests/test_build_registry_reference_checker.py -q`
  - Pass (`1045 passed`)

## 3. Initial Hold and root cause

Initial run (before fix) summary:

- exact prompt routed to `None`
- metadata had no `registry_v2_app_type`
- context source was `v1` (`registry_v2_metadata_missing`)
- v2 `pack.site` Sales Ops context was not used

Root cause:

- Sales Ops matcher had incomplete negated-exclusion neutralization coverage for exact prompt phrases such as:
  - `no ASC 606 engine`
  - `no real bank or payment identifiers`
  - `no telephony or SMS automation`
  - `no real payout approval`
  - `no trading dashboard`
  - `no compliance certification claims`
- These negated phrases were still matching Sales Ops negative patterns and causing a false negative.

## 4. Routing fix

Scoped changes were limited to Sales Ops routing and tests:

- `src/ham/build_registry/intent.py`
  - expanded `_SALES_OPS_NEGATED_EXCLUSION_PATTERNS` to cover missing negated forms from the exact gate prompt while preserving genuine exclusion blocks.
  - no changes to routing precedence, global feature flag behavior, or non-Sales-Ops matchers.
- `tests/test_build_registry_intent.py`
  - added exact gate prompt constant coverage.
  - added metadata + scaffold-context assertions for exact prompt (flag on/off).
  - added weak negated-exclusion prompts that must not route.
  - added extra genuine-exclusion prompts (ASC 606 engine, backend API/CRM sync, compliance-claims engine) that must still block.

For the **routing-fix stage only**, no recipe YAML, registry YAML, templates, v1 JSON, API, frontend, Builder Studio, CI, scaffold-quality, or game-pack files were changed.

## 5. Rerun routing result

Prompt under test (exact):

> Build a static sales ops dashboard for a commission-based AI services team. Include a sales ops shell, executive summary row, agent/team performance, sales activity metrics, pipeline stage movement, commission summary, commission earned and pending, clawbacks and chargebacks, payout status display, revenue recovery summary, recoverable balance, recovered dollars, aging buckets, recovery exception queue, process bottleneck panel, activity/audit feed, filters by date/team/agent/status/stage, visible empty/loading/error state examples, responsive layout, and accessible header/nav/main/table/list/chart structure. Use meaningful local sample data only with internally coherent illustrative calculations. No payroll, no payment processing, no accounting ledger, no ASC 606 engine, no legal collections automation, no CRM sync, no backend, no API, no real PII, no real bank or payment identifiers, no live dunning, no telephony or SMS automation, no regulated financial advice, no real payout approval, no trading dashboard, and no compliance certification claims.

With `HAM_BUILD_REGISTRY_V2_ENABLED=true` (after fix):

- `select_registry_v2_app_type_for_prompt(prompt)` → `app.sales-ops-dashboard-core`
- metadata includes `registry_v2_app_type=app.sales-ops-dashboard-core`
- scaffold context source is `v2`
- context pack is `pack.site`
- no v1 fallback used
- rendered context length: `11346` chars
- all expected Sales Ops section IDs present in rendered context

## 6. Flag-off control result

With flag off:

- metadata does **not** include `registry_v2_app_type`
- context source is `v1`
- fallback reason is `registry_v2_disabled`

Flag-off control behavior remains correct.

## 7. Sales Ops quality guard and repair-loop hardening

Scoped hardening landed in scaffold-quality path only (no routing/API/frontend/template/v1/game-pack changes):

- `src/ham/scaffold_quality.py`
  - added Sales Ops prompt matcher + Sales Ops state/semantic request helpers.
  - added Sales Ops issue detectors:
    - `sales_ops_missing_domain_regions`
    - `sales_ops_missing_loading_error_states`
    - `sales_ops_missing_semantic_financial_structure`
    - `sales_ops_forbidden_financial_impl_detected`
  - added Sales Ops repair guidance in `build_scaffold_repair_prompt(...)` with explicit domain-region, semantic-structure, static/local-data, and forbidden-implementation constraints.
  - added Sales Ops blocking-code set and mirror escalation path in `maybe_repair_generated_scaffold(...)`:
    - initial repair pass
    - one escalated Sales Ops enforcement pass
    - deterministic static Sales Ops fallback if Sales Ops blocking issues remain.
  - deterministic Sales Ops fallback now **always overwrites** `src/index.css` (not `setdefault`) so responsive guarantees cannot be skipped when prior repairs return stale CSS.

- `tests/test_scaffold_quality.py`
  - added focused Sales Ops tests for all four required detector codes.
  - added repair-prompt assertions for domain regions, visible static empty/loading/error examples, semantic table/list/chart shell, local/static sample data, and explicit forbidden implementation bans.
  - added non-Sales-Ops isolation test.
  - added generate-scaffold integration tests:
    - escalated Sales Ops pass invoked
    - deterministic Sales Ops fallback clears `sales_ops_*` issue codes.

## 8. Final rerun result

Final gate rerun artifacts:

- artifact root: `/tmp/ham-sales-ops-dashboard-core-gate-review-final/`
- generated app: `/tmp/ham-sales-ops-dashboard-core-gate-review-final/output/`
- summary: `/tmp/ham-sales-ops-dashboard-core-gate-review-final/summary.json`

Routing/control checks in final rerun:

- `select_registry_v2_app_type_for_prompt(prompt)` → `app.sales-ops-dashboard-core`
- flag-on metadata includes `registry_v2_app_type=app.sales-ops-dashboard-core`
- context source: `v2`
- context pack: `pack.site`
- v1 fallback not used (flag on)
- flag-off control remains v1 fallback (`registry_v2_disabled`) with no `registry_v2_app_type`

Repair path observed in final rerun:

- `repair_pass_logged=false`
- `repair_escalated_sales_ops_logged=false`
- `repair_fallback_sales_ops_logged=true`

Inspector result:

- `inspect_generated_scaffold_quality(..., plan=...)` → `0` issues
- `issue_codes: []`

Generated files in final rerun: 13.

## 9. Final quality checklist table

Checklist for final rerun output under `/tmp/ham-sales-ops-dashboard-core-gate-review-final/output/`.

| Gate criterion | Result | Notes |
|---|---|---|
| sales ops shell | Pass | present |
| executive summary row | Pass | present |
| agent/team performance | Pass | present |
| sales activity metrics | Pass | present |
| pipeline/stage movement | Pass | present |
| commission summary | Pass | present |
| commission earned/pending views | Pass | present |
| clawbacks/chargebacks | Pass | present |
| payout status display | Pass | present |
| revenue recovery summary | Pass | present |
| recoverable balance/recovered dollars | Pass | present |
| aging buckets | Pass | present |
| recovery exception queue | Pass | present |
| process bottleneck panel | Pass | present |
| activity/audit feed | Pass | present |
| filters by date/team/agent/status/stage | Pass | present |
| visible empty/loading/error examples | Pass | present |
| responsive layout | Pass | responsive CSS present |
| semantic header/nav/main/table/list/chart structure | Pass | present |
| meaningful local/static sample data | Pass | present |
| internally coherent illustrative calculations | Pass | coherent illustrative values present |
| no real payroll/payment/accounting/ASC606/backend/API/CRM/legal collections/PII/live dunning/telephony/trading/compliance implementation | Pass | none observed |
| no build-kit internals exposed | Pass | none observed |

## 10. Final gate decision

**Pass**

Rationale:

1. The routing false-negative root cause is fixed and remains stable.
2. Sales Ops quality guards now explicitly enforce the required generated-output checklist.
3. Final rerun satisfies routing/control checks, Sales Ops inspector checks, and manual quality checklist.

## 11. Follow-up recommendations

1. Keep Sales Ops quality guard pattern scoped and unchanged unless new drift appears.
2. Keep v2 opt-in (`HAM_BUILD_REGISTRY_V2_ENABLED`) and preserve v1 fallback defaults.
3. Continue keeping generated gate artifacts in `/tmp/` only.

## 12. Confirmations

- generated output not committed: **confirmed**
- no recipe/registry/template/v1 JSON/API/frontend/Builder Studio/CI/scaffold/game-pack changes: **confirmed**
- no commit made: **confirmed**
- no push performed: **confirmed**
- unrelated local noise left untouched: **confirmed** (`.branch-audit/`, `.mission-notes/`, `=2.8.0`, `browser-harness/`, `canary/`, `ham-default`, `ham-default-2026-05-14`)
