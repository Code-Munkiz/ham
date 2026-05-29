# Gate Review: app.saas-dashboard-core

> **Generated-build gate · local manual reruns · review artifact only**

---

## 1. Executive summary

This report records five stages:

1. **Initial Hold** (pre-routing fix)
2. **Routing fix landed** (exact prompt routes to v2)
3. **First quality hardening** (website-pack guidance/tests + initial SaaS guard)
4. **First post-hardening rerun** (still Hold: SaaS inspector issues remained)
5. **Repair-loop hardening + final rerun** (SaaS inspector issues clear)

Final decision in this run: **Pass**.

---

## 2. Repo baseline and validation

- Branch: `main`
- Latest commit at run start: `ce8d8913` (`feat(builder): route saas dashboard recipe behind registry flag`)
- Unrelated local noise remained untouched.

Validation/test commands after repair-loop hardening:

- `python3 scripts/validate_game_pack_registry.py --pack-root docs/build-kit-registry-v2/website-pack --app-type app.saas-dashboard-core --check`
  - Pass
- `python3 scripts/check_build_registry_references.py --pack docs/build-kit-registry-v2/website-pack/registry-pack.yaml --check-orphans --check-render-budget`
  - Pass with near-budget warnings only
  - `app.saas-dashboard-core`: `11398/12000` (preferred threshold warning band, still under 12k)
  - `site.dashboard-ui-core`: `11358/12000`
- `pytest tests/test_scaffold_quality.py -q`
  - Pass (`126 passed`)
- `pytest tests/test_build_registry_intent.py tests/test_build_registry_scaffold_context.py tests/test_builder_llm_scaffold_registry_context.py tests/test_website_pack_registry.py tests/test_build_registry.py tests/test_build_registry_reference_checker.py -q`
  - Pass (`965 passed`)

---

## 3. Initial Hold (historical)

Exact gate prompt used:

> Build a static SaaS product dashboard for an AI developer platform. Include an app shell with sidebar and topbar, a workspace/project selector placeholder, usage cards, a plan/status card, recent activity, a simple project/resource list, one upgrade CTA, settings/help shortcuts, empty/loading/error state examples, responsive layout, and accessible header/nav/main/list/table structure. Use meaningful local sample data only. No backend, no auth, no billing or payments, no CRUD, no admin user management, no permissions, and no live data.

Observed before routing fix:

- `select_registry_v2_app_type_for_prompt(...)` returned `None`
- no `registry_v2_app_type` metadata
- context source fell back to `v1`
- decision: **Hold**

---

## 4. Routing fix (landed)

Scope:

- `src/ham/build_registry/intent.py`
- `tests/test_build_registry_intent.py`

Outcome:

- exact gate prompt routes to `app.saas-dashboard-core` when flag is on
- v2 context source is `pack.site`
- flag-off remains v1 fallback
- routing tests cover exact prompt + exclusions

---

## 5. First quality hardening attempt (landed)

### 5.1 Website-pack guidance and validator tightening

Updated:

- `docs/build-kit-registry-v2/website-pack/app-types/app.saas-dashboard-core.yaml`
- `docs/build-kit-registry-v2/website-pack/sections/saas-empty-loading-error-states.yaml`
- `docs/build-kit-registry-v2/website-pack/sections/saas-resource-list.yaml`
- `docs/build-kit-registry-v2/website-pack/components/resource-list.yaml`
- `docs/build-kit-registry-v2/website-pack/validators/resource-list-readable.yaml`
- `docs/build-kit-registry-v2/website-pack/validators/responsive-a11y-basics.yaml`

### 5.2 Tests

Updated:

- `tests/test_website_pack_registry.py`

Added render-context assertions for static empty/loading/error guidance and semantic table/list guidance.

### 5.3 Initial SaaS scaffold guard

Updated:

- `src/ham/scaffold_quality.py`
- `tests/test_scaffold_quality.py`

Added initial SaaS issue detection and repair focus for:

- `saas_missing_loading_error_states`
- `saas_live_fetch_impl_detected`
- `saas_missing_semantic_resource_table`

### 5.4 First rerun outcome (still Hold)

SaaS inspector still reported unresolved issues in generated output:

- `saas_missing_loading_error_states`
- `saas_live_fetch_impl_detected`
- `saas_missing_semantic_resource_table`

Decision remained **Hold** at that point.

---

## 6. Repair-loop hardening (this run)

### 6.1 Strengthened SaaS repair prompt instructions

For SaaS issue codes, repair guidance now explicitly requires:

- visible static/local empty/loading/error examples rendered in UI (not text-only),
- explicit ban on fetch/API/live-loading simulation (`/api`, `fetch`, `axios`, async backend simulation, polling, timers as fake network),
- semantic table requirement (`<table>`, `<thead>`, `<tbody>`, `<th>`, `<td>`), with table preference for this gate prompt,
- no div-soup pseudo-table.

### 6.2 Bounded repair escalation

`maybe_repair_generated_scaffold` now:

- runs initial repair pass,
- runs one **escalated SaaS-specific repair pass** when SaaS blocking issues remain,
- applies a **deterministic static SaaS fallback payload** if those same SaaS blocking issues still remain after escalation.

This keeps changes scoped to scaffold-quality repair behavior and avoids API/frontend/template changes.

### 6.3 Added focused tests

`tests/test_scaffold_quality.py` now verifies:

- SaaS repair prompt explicitly bans live-fetch/API implementation,
- SaaS repair prompt explicitly requires visible static empty/loading/error examples,
- SaaS repair prompt explicitly requires semantic table tags,
- integration path exercises escalated second repair pass,
- deterministic fallback clears SaaS issue codes when repairs still fail.

---

## 7. Final rerun

Final rerun artifact root:

- `/tmp/ham-saas-dashboard-core-gate-review-final/`

Summary artifact:

- `/tmp/ham-saas-dashboard-core-gate-review-final/summary.json`

### 7.1 Routing/context controls

From final summary:

| Check | Result |
|---|---|
| `select_registry_v2_app_type_for_prompt(prompt)` | `app.saas-dashboard-core` |
| Flag-on metadata includes `registry_v2_app_type` | yes |
| Flag-on context source | `v2` |
| Flag-on context pack | `pack.site` |
| Flag-on scaffold message contains v2 header | yes |
| Flag-off metadata includes `registry_v2_app_type` | no |
| Flag-off context source | `v1` |
| Flag-off fallback reason | `registry_v2_disabled` |

### 7.2 SaaS inspector and quality result

Final rerun output:

- generated file count: `6`
- `inspect_generated_scaffold_quality(..., plan=...)`: `0` issues
- `quality_issue_codes`: `[]`

Quality checklist in final summary: `15/15` pass.

Resolved in final output:

- visible static empty/loading/error examples present,
- no fetch/API/live-data simulation present,
- semantic project/resource table with real table structure present,
- semantic header/nav/main/list/table structure present,
- local/static sample data and bounded SaaS lane preserved.

---

## 8. Final gate decision

**Pass**

Rationale:

- routing/context gate is stable and correct,
- prior quality failures were explicitly addressed in repair-loop behavior,
- final rerun cleared all three SaaS inspector issues and satisfied checklist requirements.

---

## 9. Confirmations

- Generated output stayed under `/tmp/`.
- Generated output was not committed.
- No commit was made.
- No push was performed.
- Unrelated local noise was left untouched.
- No API/frontend/Builder Studio/CI/template/v1 JSON/game-pack changes were made.
