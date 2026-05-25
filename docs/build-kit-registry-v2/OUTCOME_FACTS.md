# Build Outcome Facts — Format (ADR-0018 Phase B)

Minimal schema for summarizing a Lane A build attempt so a future Hermes critique step can propose recipe improvements. This document is **format only** — not telemetry, not Hermes wiring.

Related: [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md), [STATUS.md](STATUS.md), [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md).

---

## 1. Purpose

**Build outcome facts** are structured, redaction-safe summaries of what happened during one build attempt (scaffold ± preview ± validation signals). They answer:

- Which recipe or kit path was used?
- Did scaffold context come from v1 or v2?
- Did scaffold, validation, or preview succeed or fail?
- Was there a v2 fallback, and why?
- Did the user ask for a follow-up edit?

Outcome facts exist so maintainers (and eventually Hermes) can **critique and propose** Build Kit changes through the controlled loop in ADR-0018. They are **not** a telemetry product, analytics pipeline, or automatic mutation trigger.

---

## 2. Non-goals

This document does **not** authorize or require:

- Runtime implementation or API fields
- Database, blob store, or log retention decisions
- Hermes integration or critique prompts
- Autonomous recipe mutation, commits, or auto-merge
- User-facing UI for build history
- Automatic PR creation
- A new service, queue, or background agent

---

## 3. Minimal outcome facts

One record per build attempt. Field names are stable identifiers for future tooling; all optional fields may be omitted when unknown.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | string | Correlates this attempt (HAM run id, chat session id, or operator-generated uuid). |
| `timestamp` | string (ISO 8601 UTC) | When the attempt completed or was summarized. |
| `recipe_id` | string \| null | Registry v2 app type id (e.g. `game.idle-incremental`) when v2 was targeted; null for pure v1. |
| `registry_pack_id` | string \| null | Pack id (e.g. `pack.game`) when v2 compose ran; null otherwise. |
| `schema_version` | string \| null | Registry schema version (e.g. `"0.1"`) when known. |
| `modules_used` | string[] | Composed module ids in dependency order when v2 succeeded; empty for v1-only. |
| `route_source` | enum | How v2 metadata was set: `manual_metadata` \| `intent_router` \| `none`. |
| `feature_flag_enabled` | boolean | Whether `HAM_BUILD_REGISTRY_V2_ENABLED` was truthy at attempt time. |
| `template_kind` | string \| null | Plan `metadata.template_kind` / v1 kit routing kind (e.g. `generic`, `tetris`). |
| `legacy_v1_fallback` | string \| null | App type `legacy_v1_fallback` or resolved v1 kit id after fallback. |
| `scaffold_context_source` | enum | Injected playbook source: `v1` \| `v2` \| `none`. |
| `scaffold_success` | boolean | Whether LLM scaffold produced usable `file_changes`. |
| `scaffold_failure_reason` | string \| null | Short code or message (e.g. `LLMScaffoldError` `error_code`, parse failure). |
| `validation_results` | object[] | Per-validator summaries when a harness exists; see shape below. |
| `preview_result` | object \| null | Preview/boot summary when available; see shape below. |
| `fallback_reason` | string \| null | v2→v1 fallback reason from scaffold resolver (e.g. `registry_v2_disabled`, `registry_v2_error:…`). |
| `user_followup_summary` | string \| null | Redacted summary of user follow-up or correction request (not full chat). |
| `files_changed_count` | integer \| null | Count of scaffold output files when known. |
| `rendered_context_chars` | integer \| null | Length of injected v1 or v2 playbook context when known. |
| `notes` | string \| null | Freeform maintainer notes (non-secret). |

### `validation_results[]` item (conceptual validators today)

```json
{
  "validator_id": "validator.passive-income-tick",
  "runner": "conceptual",
  "passed": null,
  "message": "not executed — conceptual only"
}
```

When executable harnesses exist later, set `passed` to boolean and `runner` accordingly.

### `preview_result` object

```json
{
  "boot_ok": true,
  "console_error_count": 0,
  "summary": "Preview loaded; no blocking console errors"
}
```

---

## 4. Privacy and safety

Outcome facts must be safe to attach to issues, PRs, or critique prompts:

- **Do not store secrets** — API keys, tokens, session cookies, auth headers.
- **Do not store full user prompts by default** — use intent summaries (e.g. “idle clicker with upgrades and local save”).
- **Do not store generated source code by default** — record counts and failure codes, not file bodies.
- **Summarize user intent** instead of copying sensitive or PII-bearing text.
- **Redact** env vars, credentials, private keys, and internal URLs unless explicitly approved for a private maintainer report.

If a field cannot be recorded safely, omit it or replace with a redacted placeholder.

---

## 5. Example JSON

### Successful `game.idle-incremental` (v2 scaffold)

```json
{
  "run_id": "ham-run-2026-05-22-abc123",
  "timestamp": "2026-05-22T18:40:00Z",
  "recipe_id": "game.idle-incremental",
  "registry_pack_id": "pack.game",
  "schema_version": "0.1",
  "modules_used": [
    "mechanic.score",
    "mechanic.economy",
    "mechanic.upgrades",
    "mechanic.save-load",
    "component.game-shell",
    "component.resource-counter",
    "component.save-status",
    "component.upgrade-card"
  ],
  "route_source": "intent_router",
  "feature_flag_enabled": true,
  "template_kind": "generic",
  "legacy_v1_fallback": "generic",
  "scaffold_context_source": "v2",
  "scaffold_success": true,
  "scaffold_failure_reason": null,
  "validation_results": [
    {
      "validator_id": "validator.passive-income-tick",
      "runner": "conceptual",
      "passed": null,
      "message": "not executed — conceptual only"
    }
  ],
  "preview_result": {
    "boot_ok": true,
    "console_error_count": 0,
    "summary": "Preview loaded; passive tick and save UI present"
  },
  "fallback_reason": null,
  "user_followup_summary": null,
  "files_changed_count": 8,
  "rendered_context_chars": 8822,
  "notes": "Manual smoke with HAM_BUILD_REGISTRY_V2_ENABLED=1"
}
```

### Failed scaffold with v2 fallback to v1

```json
{
  "run_id": "ham-run-2026-05-22-def456",
  "timestamp": "2026-05-22T19:05:00Z",
  "recipe_id": "game.idle-incremental",
  "registry_pack_id": "pack.game",
  "schema_version": "0.1",
  "modules_used": [],
  "route_source": "intent_router",
  "feature_flag_enabled": true,
  "template_kind": "generic",
  "legacy_v1_fallback": "generic",
  "scaffold_context_source": "v1",
  "scaffold_success": false,
  "scaffold_failure_reason": "step.step_verification_failed",
  "validation_results": [],
  "preview_result": null,
  "fallback_reason": "registry_v2_error:broken reference in composed recipe",
  "user_followup_summary": "User asked to fix save/load not persisting after refresh",
  "files_changed_count": null,
  "rendered_context_chars": null,
  "notes": "v2 compose failed; v1 generic kit context used; scaffold still failed on JSON parse"
}
```

Field values are illustrative. Producers should use actual error codes and fallback strings from runtime when implementation lands.

---

## 6. Hermes critique input

When Hermes critique is implemented (future), the **minimum input bundle** should include:

| Input | Required | Notes |
|-------|----------|-------|
| Outcome facts JSON | Yes | Full minimal record above |
| `recipe_id` + `modules_used` | When v2 | Identifies composed playbook |
| Validation failures | When present | Failed or skipped validators with ids |
| Preview failures | When present | `boot_ok: false` or console errors |
| `user_followup_summary` | When known | Redacted correction pattern |
| Relevant recipe snippets | Optional | Only affected YAML sections — not full pack |

Hermes should **not** receive full prompts, generated source trees, or secrets by default.

---

## 7. Hermes critique output

Suggested structure for a critique report (markdown or JSON — format TBD at implementation):

| Field | Description |
|-------|-------------|
| `summary` | One-paragraph assessment of build vs recipe expectations |
| `observed_issue` | Concrete failure or gap (e.g. missing save-load guidance) |
| `affected_recipe_module_ids` | App type + module ids to change |
| `proposed_change_type` | e.g. `guidance_tighten`, `add_validator`, `add_recovery`, `clarify_acceptance`, `trim_render`, `out_of_scope_note` |
| `proposed_patch_summary` | Plain-language description of YAML/doc edits — not auto-applied |
| `evidence` | Pointers to outcome facts fields (failure codes, follow-up summary) |
| `risk_level` | `low` \| `medium` \| `high` (high for safety/routing/render budget) |
| `validation_commands` | Copy-paste commands from §9 |
| `human_review_notes` | Questions for maintainer before merge |

Output is a **proposal only**. No file writes, no commits, no routing changes.

---

## 8. Evidence threshold

A recipe improvement proposal should cite **at least one** of:

- Repeated build failure pattern (same `scaffold_failure_reason` or recovery invocation)
- Validation failure (when harness exists)
- Preview failure (`boot_ok: false`, recurring console errors)
- User correction / edit pattern (same topic in `user_followup_summary` twice)
- Maintainer observation (manual smoke, review note in `notes`)

Single-incident proposals are allowed for **high-severity** issues (safety constraint gap, broken module reference) with explicit `risk_level: high`.

---

## 9. Validation gates

Any proposed recipe change must pass before human merge:

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type <affected-app-type> \
  --check
```

```bash
pytest tests/test_build_registry.py -q
```

Additional gates (unchanged from ADR-0018 and Authoring Guide):

- Rendered playbook context ≤ 12,000 characters (default budget)
- No orphan YAML (every file in `registry-pack.yaml` `module_index`)
- No unresolved references or dependency cycles
- No templates or starter source files added
- Re-validate **all affected app types** after shared module edits

---

## 10. Relationship to ADR-0018

ADR-0018 defines the controlled evolution loop:

```txt
Build attempt → outcome facts → Hermes critique → proposed recipe change
  → validation/tests → human review → normal commit/merge
```

This document standardizes the **outcome facts** artifact (Phase B). It does not implement critique, patches, or merge. Outcome facts are the evidence-shaped handoff between “what happened on a build” and “what Hermes might suggest changing in YAML.”

---

## 11. Future implementation path

Conservative rollout — no autonomous mutation at any phase:

| Phase | Deliverable |
|-------|-------------|
| **1 — Docs format** | This file (`OUTCOME_FACTS.md`) |
| **2 — Manual markdown report** | Operator fills a template from build notes |
| **3 — Local generator script** | Optional script reads existing logs/artifacts → outcome JSON (no new service) |
| **4 — Hermes critique prompt** | Operator-triggered critique over outcome facts + optional snippets |
| **5 — Human-reviewed patch proposal** | Hermes drafts suggested diff; maintainer validates and merges |

Storage location (issue comment, `.ham/` artifact, PR attachment) remains an open decision — see [STATUS.md §9](STATUS.md#9-next-recommended-steps).
