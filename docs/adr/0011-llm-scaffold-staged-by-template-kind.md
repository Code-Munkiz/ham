# 0011 — LLM-generated scaffolds replace deterministic templates staged by template kind, not in one big-bang PR

## Status

**Partially superseded (historical record).**

The **staged migration decision below** was the correct call at the time. The **legacy deterministic scaffold runtime path was later retired** (`refactor(builder): retire legacy deterministic scaffolds`). **Current runtime (Lane A):** every app archetype — including calculator and tetris — routes through **LLM-generated scaffolds** in `src/ham/builder_llm_scaffold.py`, guided by **Builder Kit metadata** (`src/ham/data/builder_kits/*.json`). HAM does **not** clone checked-in starter file trees per kit.

See also:

- [`docs/PHASE_2_DESIGN.md`](../PHASE_2_DESIGN.md) § Subsystem 9 — current scaffold + kit behavior
- [`docs/adr/0016-generative-build-kit-registry-v2.md`](0016-generative-build-kit-registry-v2.md) — **proposed** next-generation composable registry (not implemented)

**Naming debt:** code and Plan metadata still use `template_kind` for app-archetype ids (e.g. `landing-page`, `tetris`). That is an **archetype label**, not a file template or clone baseline.

---

## Original decision (historical record)

Tier 1 #2 calls out the deterministic template-driven scaffold in `src/ham/builder_chat_scaffold.py` (~1400 LoC) as the second-largest gap toward Manus/Replit parity — it works for the existing calculator and tetris kinds but cannot synthesize arbitrary builder requests. Phase 2 introduces an LLM-driven scaffold path to fill that gap. We had to decide whether to land it as one big-bang replacement (delete the deterministic path; route everything through the new LLM path) or as a staged migration. We chose **staged by template kind**: ship the LLM path alongside the deterministic path, route NEW template kinds (todo app, dashboard, landing page, anything not in the existing template set) through the LLM path, leave calculator and tetris on the deterministic path for now, and migrate the existing kinds only after the verifier (Phase 1 #19) has built confidence over real usage.

## Why staged over big-bang

`builder_chat_scaffold.py` is the existing happy path for the templates HAM users actually exercise today (calculator, tetris). If the LLM-scaffold path regresses against those kinds, all builder traffic breaks — even traffic that has nothing to do with the new feature. The big-bang approach trades a smaller end-state codebase for a much wider blast radius the day the PR merges. The staged approach defers the deterministic-path deletion until we have real evidence the LLM path matches or exceeds it on the existing kinds.

## Why kind-based routing instead of feature flag

A feature flag would gate the new path globally per user / per project. The kind-based router gates per template, which is the dimension that actually matters: the LLM path's behavior is consistent within a kind but can drift between kinds. The verifier (Phase 1 #19) runs once at the end of every Plan (per Phase 2a decision) and is the natural fitness function for kind-level confidence — if the LLM-scaffold path's success rate on calculator stays above some threshold across N runs, the migration to LLM-only-on-calculator becomes evidence-driven rather than calendar-driven.

## Consequences

- Phase 2 ships `src/ham/builder_llm_scaffold.py` (or analogous) alongside the existing `builder_chat_scaffold.py`; both modules coexist
- A router (probably inside the Worker's step-execution path) picks based on the active template kind: if kind in {`calculator`, `tetris`} → deterministic; else → LLM-scaffold
- The verifier (Phase 1 #19) is the gate for trusting LLM-scaffold output before a Plan is marked complete; failure surfaces as `step.step_verification_failed`
- Tier 2 follow-up work covers: A/B testing LLM vs deterministic on calculator with verifier-graded success rates; deprecating the deterministic path one kind at a time
- The `builder_chat_scaffold.py` ~1400 LoC stays as-is through Phase 2; it is NOT a refactor target
- Reversing this ADR (deciding mid-migration to bigh-bang) is a routing-config change plus a deletion PR — not a wire-format or contract change

---

## Supersession note (post-retirement)

After this ADR landed, the team completed the migration **for all kinds** (including calculator and tetris) to the LLM scaffold path. `src/ham/builder_template_kinds.py` keeps an empty `_REGISTRY`; `select_scaffold_path()` always returns `"llm"`. The deterministic generator helpers in `builder_chat_scaffold.py` are **retired at runtime**; that module now owns snapshot/ZIP/artifact orchestration for chat scaffolds.

**Builder Kits** (v1) are **generative playbook metadata** injected into the LLM scaffold prompt — not starter templates. A deeper composable registry is proposed in ADR-0016; it is **not wired**.
