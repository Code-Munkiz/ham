# Build Registry v2 DOM-Native Game-Kit Completion Checkpoint

Closeout checkpoint after the planned **DOM-native game-kit phase** completed on `origin/main`. This document **closes the DOM-native Game Pack expansion track** — it is **not** approval for new recipes, routing changes, runtime enablement, default v2 rollout, Canvas/physics kits, or website/design-system implementation. For live status see [STATUS.md](STATUS.md).

**Checkpoint:** `origin/main` at `c73c8877` — **16 recipes**, **376 indexed modules**, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

**Latest closeout commit:** `c73c8877` — `fix(builder): close city builder generated quality gate`

---

## 1. Executive summary

**The DOM-native game-kit phase is complete.**

- Build Registry v2 Game Pack now has **16 recipes** and **376 indexed modules** — idle through strategy/sim, all DOM-native patterns.
- **All sixteen recipes are narrowly routable** behind `HAM_BUILD_REGISTRY_V2_ENABLED` when prompt intent clearly matches each recipe’s conservative signals.
- **v1 Builder Kits remain the default** when the flag is unset or false.
- **No templates or starter source files** were created — recipes remain generative playbooks only.
- **No generated app output has been committed** — all gate artifacts remain under `/tmp/` only.
- **No API, frontend, or Builder Studio changes** were made during this phase closeout.
- **Reference checker is clean** — local/manual `scripts/check_build_registry_references.py` reports 0 errors / 0 warnings on full orphan + render-budget pass.
- **Canvas/physics kits are deferred** to a separate ADR/design track.
- **Ready to transition** toward **website/design-system build-kit work** — direction/readiness first, not implementation from this checkpoint.

---

## 2. Completed DOM-native recipes

| Recipe | Wave | Status | Routing | Gate result | Key loop proven |
|--------|------|--------|---------|-------------|-----------------|
| `game.idle-incremental` | 1 | Validated + routed | Behind flag | Pilot validated (no gate review doc) | Earn / upgrade / passive income tick |
| `game.trivia-timer` | 1 | Validated + routed | Behind flag | Pilot validated (no gate review doc) | Timed quiz question → answer → score |
| `game.branching-narrative` | 1 | Validated + routed | Behind flag | Pilot validated (no gate review doc) | Choice → branch → story state |
| `game.memory-match` | 1 | Validated + routed | Behind flag | Pilot validated (no gate review doc) | Flip cards → pair match → win |
| `game.word-daily` | 1 | Validated + routed | Behind flag | Pilot validated (no gate review doc) | Daily word guess → letter feedback |
| `game.daily-puzzle-grid` | 2 | Validated + routed | Behind flag | Pilot validated (no gate review doc) | Grid/logic cell rules → solve |
| `game.resource-management-sim` | 2 | Validated + routed | Behind flag | Manual outcome review (pattern-only) | Resource pools → allocation → win/loss |
| `game.hangman-lite` | 2 | Validated + routed | Behind flag | Pilot validated (no gate review doc) | Letter guess → word reveal → result |
| `game.typing-speed-racer` | 2 | Validated + routed | Behind flag | Manual outcome review (pattern-only) | Typing prompt → WPM/accuracy → result |
| `game.word-builder` | 2 | Validated + routed | Behind flag | Manual outcome review (pattern-only) | Letter pool → valid word submit → score |
| `game.card-deck-turn-based` | 3 | Validated + routed | Behind flag | **Pass** — [wave3-gate-fix-review](./outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md) | Draw/hand/discard → play card → enemy turn → win |
| `game.reaction-time-challenge` | 3 | Validated + routed | Behind flag | **Pass** — [wave3-gate-review](./outcome-reports/game.reaction-time-challenge.wave3-gate-review.md) | Wait → signal → reaction ms → result |
| `game.rhythm-tap-lite` | 3 | Validated + routed | Behind flag | **Pass** — [wave3-gate-review](./outcome-reports/game.rhythm-tap-lite.wave3-gate-review.md) | Beat cue → tap window → combo/streak → result |
| `game.deck-builder-lite` | 3 | Validated + routed | Behind flag | **Pass** — [wave3-gate-review](./outcome-reports/game.deck-builder-lite.wave3-gate-review.md) | Starter deck → encounter → reward → deck mutation → run result |
| `game.turn-based-tactics-lite` | 4 | Validated + routed | Behind flag | **Pass** — [wave4-gate-review](./outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md) | Select unit → move in range → attack → enemy turn → win/loss → restart |
| `game.city-builder-lite` | 4 | Validated + routed | Behind flag | **Pass** — [wave4-gate-review](./outcome-reports/game.city-builder-lite.wave4-gate-review.md) | Building palette → grid placement → day production → population/happiness → goal/fail → restart |

**Wave inventory:** Wave 1 (5) · Wave 2 (5) · Wave 3 (4) · Wave 4 (2) = **16 recipes**.

---

## 3. Quality system now in place

The DOM-native phase established a repeatable **quality rhythm** beyond schema validation:

| Mechanism | Role |
|-----------|------|
| **Scaffold quality repair guard** | `inspect_generated_scaffold_quality()` + optional one-pass `maybe_repair_generated_scaffold()` in the scaffold pipeline; `HAM_SCAFFOLD_QUALITY_REPAIR=false` disables repair |
| **[Gameplay quality principles](./GAMEPLAY_QUALITY_PRINCIPLES.md)** | Persistent doctrine — playable loops, anti-patterns, family-specific expectations, when to add detectors |
| **Reference checker** | `scripts/check_build_registry_references.py` — pack refs, duplicates, orphans, render-budget headroom; local/manual, not CI-blocking |
| **Render-budget trim** | Near-budget recipes tightened while preserving core mechanics; all sixteen renders stay below 12k cap |
| **Generated gate reviews** | Local `/tmp/` operator runs via established scaffold APIs; outcome reports under [outcome-reports/](./outcome-reports/) |
| **Anti-pattern detector rhythm** | Schema-first → validate/compose/render → explicit routing approval → `/tmp/` generated gate review → scaffold quality guard extension → outcome report → tests |

**Family-specific guard coverage landed during this phase:**

- Card/deck: seed, victory, reward pools, discard wiring, run result/restart
- Arcade timing: timer/result, rhythm miss/combo, reaction false-start
- Tactics: select/move/attack dispatch, movement/attack range, enemy turn, immutable HP, restart reseed
- City-builder: building palette, placement guards, grid-derived production, population/happiness derivation, goal/fail/restart

---

## 4. Final Wave 4 status

Wave 4 closed the strategy/sim lane with two recipes — both **Pass** on final generated gate reviews:

| Recipe | Final gate | Gaps closed |
|--------|------------|-------------|
| **`game.turn-based-tactics-lite`** | **Pass** | Attack wiring (`ATTACK` dispatch), attack range checks, enemy turn, win/loss/restart — see [wave4-gate-review](./outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md) |
| **`game.city-builder-lite`** | **Pass** | Building palette/placement, grid-derived food/coins production, population mutation, **happiness derived from wells/power/food pressure** (not hardcoded `happinessChange = 1`) — see [wave4-gate-review](./outcome-reports/game.city-builder-lite.wave4-gate-review.md) |

**Wave 4 closeout commits (representative):**

- `7909f9e8` / routing lands — turn-based tactics recipe + routing
- `4e532c2d` — close turn-based tactics generated quality gate
- `e2fb943c` — city builder lite recipe
- `62d6bdc6` — route city builder recipe behind registry flag
- `c73c8877` — close city builder generated quality gate

---

## 5. Current constraints / posture

| Constraint | Posture |
|------------|---------|
| **Rendering model** | **DOM-native only** for Game Pack — React/Vite-style grids, cards, timers, text, buttons, panels |
| **Canvas / physics** | **Deferred** — separate ADR/design track; not mixed into DOM-native pack without explicit approval |
| **State architecture** | **No ECS hard mandate** — FSM-lite / reducer / hook state patterns adopted in generated output and guard expectations |
| **Registry v2 default** | **Off** — `HAM_BUILD_REGISTRY_V2_ENABLED` must be truthy for v2 routing and playbook context |
| **Public kit picker** | **None** — no user-facing recipe browser in product UI |
| **Approval rhythm** | **Route-after-approval preserved** — schema land → validate/compose/render → routing PR → generated gate → quality guard → docs |
| **Generated output** | **Never committed** — gate artifacts under `/tmp/` only |
| **Templates / starters** | **None** — generative playbooks only |
| **CI** | Reference checker **not** CI-blocking; registry pytest suites run warning-only in CI |

---

## 6. Deferred game candidates

Do **not** treat these as approved next recipes from this checkpoint:

| Candidate | Why deferred |
|-----------|--------------|
| **Canvas / physics recipes** | Separate rendering/runtime lane; needs ADR beyond DOM-native pack |
| **Multiplayer / PvP** | Out of scope for current scaffold quality model and safety posture |
| **Live AI NPC / story systems** | Branching narrative covers static CYOA; live AI dungeon explicitly excluded from routing |
| **Deeper RTS / tower defense / factory automation** | Broader sim/combat scope; city-builder and tactics prove bounded loops only |
| **City-builder expansion beyond core loop** | Core placement/production/population/happiness/goal/restart proven; zoning, traffic, disasters, etc. are future lanes |

---

## 7. Recommended next workstream

**Move to website/design-system build-kit work.**

Start with a **direction/readiness document** — not implementation, not new recipes, not routing from this checkpoint.

**Carry forward lessons from gameplay kits:**

| Lesson | Apply to website/design-system kits |
|--------|--------------------------------------|
| **Persistent doctrine docs** | e.g. layout/accessibility/component-quality principles parallel to [GAMEPLAY_QUALITY_PRINCIPLES.md](./GAMEPLAY_QUALITY_PRINCIPLES.md) |
| **Anti-pattern taxonomy** | Document unacceptable generated UI patterns before adding detectors |
| **Generated gate criteria** | Define representative prompts + pass/fail checklist per kit family |
| **Reference checking** | Extend checker patterns as module count grows |
| **Test-first posture** | Routing/intent tests + focused scaffold-quality tests before declaring a kit “Pass” |

**Do not** enable Build Registry v2 by default or add a public kit picker as part of the next workstream kickoff.

---

## 8. Non-goals

This checkpoint does **not** authorize or imply:

- New Game Pack recipes from this document alone
- Routing changes from this document alone
- CI workflow changes (reference checker promotion, blocking gates)
- Runtime, API, frontend, Builder Studio, or scaffold pipeline changes
- Canvas, physics, or ECS-mandated architecture
- Website or design-system **implementation** — direction/readiness only
- Default v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` remains off by default)
- Committing generated app output

---

## 9. References

| Doc | Purpose |
|-----|---------|
| [GAMEPLAY_QUALITY_PRINCIPLES.md](./GAMEPLAY_QUALITY_PRINCIPLES.md) | Persistent generated gameplay quality doctrine |
| [WAVE_3_COMPLETION_CHECKPOINT.md](./WAVE_3_COMPLETION_CHECKPOINT.md) | Wave 3 closeout — card/deck + arcade timing |
| [WAVE_4_STRATEGY_SIM_DIRECTION.md](./WAVE_4_STRATEGY_SIM_DIRECTION.md) | Wave 4 strategy/sim direction and prerequisites |
| [CITY_BUILDER_LITE_READINESS_REVIEW.md](./CITY_BUILDER_LITE_READINESS_REVIEW.md) | City-builder readiness before schema land |
| [TACTICS_GRID_AMBIGUITY_REVIEW.md](./TACTICS_GRID_AMBIGUITY_REVIEW.md) | Tactics routing ambiguity review |
| [STATUS.md](./STATUS.md) | Live registry status and validation commands |
| [outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md](./outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md) | Wave 4 tactics generated gate — **Pass** |
| [outcome-reports/game.city-builder-lite.wave4-gate-review.md](./outcome-reports/game.city-builder-lite.wave4-gate-review.md) | Wave 4 city-builder generated gate — **Pass** |
| [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](./REGISTRY_REFERENCE_CHECKER_PROPOSAL.md) | Reference checker design proposal |
| [REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md](./REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md) | Reference checker implementation plan |
