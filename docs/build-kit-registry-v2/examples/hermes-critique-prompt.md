# Manual Hermes Critique Prompt for Build Kit Evolution

> **Example / manual prompt · Not runtime wiring · Not telemetry · Not an autonomous agent workflow · Not permission for Hermes to edit files directly**

---

## Status note

This is a **manually authored prompt template** for future Build Kit evolution workflows (ADR-0018 Phase C). A human operator copies the prompt below into a Hermes or LLM session together with an outcome facts report.

**HAM does not execute this prompt today.** It does **not** grant Hermes permission to edit recipe YAML, open PRs, change routing, or merge changes. All recipe edits remain normal human-reviewed git commits.

---

## When to use this prompt

**Use it when:**

- A build **outcome facts** report exists (JSON or markdown summary per [OUTCOME_FACTS.md](../OUTCOME_FACTS.md))
- A maintainer wants Hermes to **critique** the run and assess whether a recipe/module improvement is justified
- The goal is a **proposal** for human review — not an automatic patch

**Do not use it for:**

- Automatic recipe mutation or live production YAML edits
- Autonomous commits or auto-merge
- Routing changes without explicit approval (see [AUTHORING_GUIDE.md](../AUTHORING_GUIDE.md))
- Replacing registry validation or pytest gates
- Background agents or continuous auto-critique loops

---

## Required inputs

Gather before sending the prompt:

| Input | Required | Notes |
|-------|----------|-------|
| Outcome facts report | Yes | JSON or markdown; see [OUTCOME_FACTS.md](../OUTCOME_FACTS.md) |
| Affected `recipe_id` | Yes | e.g. `game.idle-incremental` |
| `modules_used` | When v2 | Composed module ids from outcome facts |
| Validation failures | If any | Validator id + pass/fail/message |
| Preview failures | If any | `boot_ok: false`, console errors |
| `user_followup_summary` | If any | Redacted correction pattern — not full chat |
| Relevant recipe snippets | Optional | Only affected YAML sections — not full pack |
| Validation commands | Yes | Copy from outcome facts or § below |

**Do not attach:** full user prompts, generated source trees, secrets, API keys, or env dumps.

**Default validation commands** (substitute `<affected-app-type>`):

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type <affected-app-type> \
  --check
```

```bash
pytest tests/test_build_registry.py -q
```

---

## The prompt

Copy the block below. Replace the placeholder sections with your outcome facts and optional recipe snippets.

```text
You are reviewing a HAM Build Registry v2 build attempt for recipe improvement purposes only.

This is a CRITIQUE task — not an execution task. You must NOT edit files, commit changes, open PRs, or propose routing changes unless explicitly separated and flagged for human approval.

## Outcome facts

<PASTE OUTCOME FACTS JSON OR MARKDOWN SUMMARY HERE>

## Affected recipe

- recipe_id: <RECIPE_ID>
- modules_used: <LIST OR "see outcome facts">

## Optional recipe snippets (affected modules only)

<PASTE ONLY RELEVANT YAML SECTIONS, OR WRITE "none">

## Validation commands (must be included in your output)

python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type <AFFECTED_APP_TYPE> \
  --check

pytest tests/test_build_registry.py -q

---

## Your instructions

1. Read the outcome facts carefully. Treat them as the primary evidence.
2. Decide whether there is **enough evidence** to recommend a Build Kit recipe/module change.
3. **Prefer "No change recommended" or "Needs more evidence"** when:
   - The build succeeded and evidence is a single user follow-up
   - There is no validation or preview failure
   - There is no repeated failure pattern
   - Evidence is anecdotal or one-off
4. **Never** propose:
   - Direct production mutation or auto-applied patches
   - Templates, starter source files, or clone baselines
   - Casual removal or weakening of safety_constraints
   - Routing changes bundled with recipe guidance changes
   - Marking conceptual validators as executable without a separate implementation task
5. **Separate** recipe/module guidance changes from routing changes. Routing requires explicit approval.
6. **Cite evidence** from the outcome facts (field names, failure codes, follow-up summary).
7. Identify **affected recipe/module ids** only when a change is justified.
8. Propose a **small patch summary** in plain language only if justified — not a full YAML rewrite.
9. Provide **validation commands** the maintainer must run before any merge.
10. Assign **risk level**: Low | Medium | High (High for safety, routing, render budget >12k, or broken references).
11. Include **human review notes** — questions or blockers for the maintainer.

Respond in the markdown format defined below. Be conservative.
```

---

## Expected Hermes output format

Hermes (or the reviewing LLM) should respond in this markdown structure:

```markdown
# Build Kit Critique

## Recommendation
No change recommended | Change recommended | Needs more evidence

## Evidence
- <bullet citing outcome facts fields, e.g. scaffold_failure_reason, user_followup_summary>
- ...

## Affected recipe/modules
- <recipe_id>
- <module_id>
- ...

## Observed issue
<Plain-language description, or "None — build succeeded" if applicable>

## Proposed change
<Small patch summary in plain language, or "None">

## Proposed change type
<guidance_tighten | add_validator | add_recovery | clarify_acceptance | trim_render | out_of_scope_note | none>

## Risk level
Low | Medium | High

## Validation commands
```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type <affected-app-type> \
  --check
```

```bash
pytest tests/test_build_registry.py -q
```

## Human review notes
- <questions, blockers, or "Single incident — do not merge recipe change from this report alone">
```

**Output is a proposal only.** The maintainer validates, edits YAML manually if needed, runs commands, and merges through normal git review.

---

## Evidence threshold (quick reference)

Recommend **Change recommended** only when at least one applies (see [OUTCOME_FACTS.md §8](../OUTCOME_FACTS.md#8-evidence-threshold)):

- Repeated build failure pattern (same `scaffold_failure_reason`)
- Validation failure (when harness exists)
- Preview failure (`boot_ok: false`)
- User correction pattern (same topic twice in follow-ups)
- Maintainer observation with concrete gap (broken ref, recovery missing)
- Single **high-severity** issue (safety constraint gap, broken module reference) — mark **High** risk

A **single successful build** with one optional follow-up → default to **No change recommended** or **Needs more evidence**.

---

## Example usage

1. Start from a manual outcome report, e.g. [idle-incremental-success-example.md](outcome-facts/idle-incremental-success-example.md).
2. Paste the outcome facts JSON into the prompt placeholder.
3. Set `recipe_id` to `game.idle-incremental` and list `modules_used` from the report.
4. Run the prompt in a Hermes or operator LLM session (manual — not HAM API).
5. Expect **No change recommended** or a low-risk guidance note only — not an automatic recipe edit.

---

## Related docs

- [OUTCOME_FACTS.md](../OUTCOME_FACTS.md) — outcome facts schema
- [ADR-0018: Build Kit Evolution Loop with Hermes](../../adr/0018-build-kit-evolution-loop-with-hermes.md)
- [AUTHORING_GUIDE.md](../AUTHORING_GUIDE.md)
- [STATUS.md](../STATUS.md)
- [idle-incremental-success-example.md](outcome-facts/idle-incremental-success-example.md) — sample outcome report
