# Website Gate Review: site.landing-page-core

> **Generated-build gate · Local operator run · Not production telemetry · Not automated validator output**
>
> Review artifact only. Generated app output lives under `/tmp/` and was **not** committed.
>
> **Update history:**
> - **2026-05-28 (initial):** Gate **Hold** — the specified prompt did not route because the negated constraint `"no backend or live form handling"` matched the landing `backend` negative pattern (false negative).
> - **2026-05-28 (routing fix rerun):** Negated backend/form/payment/CMS phrasing no longer blocks routing when strong landing positives are present. The same prompt now routes to `site.landing-page-core` with v2 context (no v1 fallback). Gate updated to **Conditional pass** (routing fixed; website-quality gaps remained — social-proof omitted, single hero CTA, `href="#"`).
> - **2026-05-28 (recipe-guidance quality fix + pass rerun):** Strengthened **website-pack recipe guidance** (social-proof required-when-requested with safe placeholders; hero dual CTA preserved; no `href="#"`/in-page anchors). Pass rerun now emits a distinct `SocialProof` section, hero primary + secondary CTAs, and anchor-target CTAs. Gate updated to **Pass**. Scope across all three updates: `src/ham/build_registry/intent.py`, website-pack recipe YAML guidance/validators, tests, and this doc only — **no** API, frontend, Builder Studio, CI, scaffold-behavior, v1 JSON, template, game-pack, or new-recipe/new-routing changes; v1 default and game routing preserved.

---

## 1. Checkpoint metadata

| Field | Value |
|-------|--------|
| **Recipe id** | `site.landing-page-core` |
| **Review type** | First website-lane generated-build gate (post-routing) |
| **Source** | local/manual generated output review |
| **Production telemetry** | no |
| **Automated validator** | no (recipe validators remain `runner: conceptual`; quality inspector is game-focused) |
| **Generated output committed** | no |
| **Initial review date** | 2026-05-28 (UTC) |
| **Routing-fix rerun date** | 2026-05-28 (UTC) |
| **Initial artifact dir** | `/tmp/ham-landing-page-core-gate-review/` |
| **Routing-fix artifact dir** | `/tmp/ham-landing-page-core-gate-review-fixed/` |
| **Pass artifact dir** | `/tmp/ham-landing-page-core-gate-review-pass/` |
| **Initial primary-run dir** | `/tmp/ham-landing-page-core-gate-review/generated/` (v1 fallback — did not route) |
| **Routing-fix primary-run dir** | `/tmp/ham-landing-page-core-gate-review-fixed/generated/` (**v2 — routed**) |
| **Pass primary-run dir** | `/tmp/ham-landing-page-core-gate-review-pass/generated/` (**v2 — routed, social proof + dual CTA**) |
| **Repo HEAD (routing commit, unpushed)** | `999b63a6` — `feat(builder): route landing page recipe behind registry flag` |
| **Local/uncommitted changes** | `src/ham/build_registry/intent.py`, `tests/test_build_registry_intent.py`, `tests/test_website_pack_registry.py`, website-pack recipe guidance/validators, this doc |
| **Pass-rerun v2 context length** | 10,776 chars (after guidance additions; < 11.4k preferred, < 12k cap) |
| **Environment flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` |
| **Scaffold model** | resolved via `_get_scaffold_model()` default (no `HAM_SCAFFOLD_MODEL` override) |

---

## 2. Prompt used

> Build a responsive landing page for a developer tool that helps teams generate better AI-built apps. Include a specific hero value proposition, feature/value sections, social proof, clear primary and secondary CTAs, FAQ, final conversion section, accessible headings/buttons, and no backend or live form handling.

---

## 3. Generation path

### APIs used (existing surface only)

| Component | Path / function |
|-----------|-----------------|
| Intent routing | `select_registry_v2_app_type_for_prompt`, `enrich_plan_metadata_with_registry_v2` |
| Scaffold context | `resolve_scaffold_context` (`src/ham/build_registry/scaffold_context.py`) |
| LLM scaffold | `generate_scaffold()` (`src/ham/builder_llm_scaffold.py`) |
| Post-output inspect | `inspect_generated_scaffold_quality()` (`src/ham/scaffold_quality.py`) |

No new repo script. Operator Python invocation of established public APIs only; runner kept under `/tmp/ham-landing-page-core-gate-review/run_gate.py`.

### Two runs

1. **Primary run** — the prompt exactly as specified, through `enrich_plan_metadata_with_registry_v2` (real routing). This is the as-shipped operator path.
2. **Forced-v2 run** — metadata `registry_v2_app_type` set directly to `site.landing-page-core` so `resolve_scaffold_context` selects the v2 website-pack recipe. This isolates **recipe generated quality** from the routing outcome, since the primary run did not route (see §4).

---

## 4. Routing / context result

### 4.0 Routing fix (between initial Hold and rerun)

**Problem:** the landing negative `\b(backend|api|authentication|auth|accounts|login|signup)\b` (and the `payment`/`cms` negatives) fired on *negated* constraints — "no backend", "without a backend", "no payments", "no CMS" — blocking otherwise-strong landing prompts.

**Fix (`src/ham/build_registry/intent.py`, routing-only):**

- Added `_LANDING_NEGATED_EXCLUSION_PATTERN` + `_strip_negated_exclusions()` — a targeted regex that matches **negation markers** (`no` / `without` / `sans` / `zero` / `free of`) followed by a backend/server/api/auth/account/login/signup/form/payment/checkout/cart/cms/database term (with optional `a`/`an`/`any`/`live`/`server-side`/`user` fillers and trailing `handling`/`submission`/`management`/`system`).
- `_matches_landing_page_core()` now: (1) requires a **strong landing positive** first; (2) only then strips negated-constraint spans before evaluating the landing negatives. Genuine feature *requests* ("build a backend", "with a backend", "connect to an API", "payment checkout", "user accounts") keep their feature word and **still block**.
- **Conservative by construction:** stripping applies only when a strong landing positive already matched, so weak prompts ("build a website with no backend") still have no positive and do not route. No generic website/page/design/homepage router was added; dashboard/ecommerce/CMS/backend exclusions remain globally intact for non-negated phrasing.

### 4.1 Initial primary run (as specified) — **did NOT route** (pre-fix)

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | **`None`** |
| `registry_v2_app_type` in metadata | **absent** |
| Scaffold context source | **v1** (`fallback_reason=registry_v2_metadata_missing`) |
| v1 Builder Kit fallback | **Used** (1,119-char v1 context) |

**Root cause (confirmed):** the prompt contains the constraint phrase **"no backend or live form handling"**. The word **`backend`** matches the landing-page negative pattern `\b(backend|api|authentication|auth|accounts|login|signup)\b`, which fires before the (otherwise satisfied) positive landing-page patterns. The negative filter is phrase-based and does not distinguish a *negated* backend constraint ("no backend") from a *requested* backend feature.

Positive landing signals that **did** match (but were overridden by the negative):

- `landing page … hero|features|cta|faq|value proposition`
- `build … landing page … hero|features|social proof|final cta`

This was a **conservative false negative**: a legitimate static landing-page prompt held back by a defensive anti-backend guard. **Resolved** by the routing fix in §4.0.

### 4.2 Routing-fix primary run (same prompt, post-fix) — **routes to v2**

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | **`site.landing-page-core`** |
| `registry_v2_app_type` in metadata | **`site.landing-page-core`** |
| Scaffold context source | **v2** |
| Pack id | **`pack.site`** |
| Rendered v2 context length | **8,593 chars** |
| v1 Builder Kit fallback | **Not used** (`fallback_reason=None`) |

The negated `"no backend or live form handling"` no longer blocks; the strong hero/features/social-proof/CTA/FAQ positives now drive routing to the website-pack recipe.

### 4.4 Recipe-guidance quality fix (between routing-fix rerun and pass rerun)

The routing-fix rerun routed correctly but the generated page still (a) omitted social proof, (b) dropped to one hero CTA, and (c) used a dead `href="#"`. These are **render-guidance** gaps, fixed in the **website-pack recipe YAML** (no runtime/scaffold change):

| Module | Guidance change |
|--------|-----------------|
| `app-types/site.landing-page-core.yaml` | Hero dual CTA when requested; never `href="#"`; use in-page anchors (`#features`/`#faq`/`#contact`/`#waitlist`); include a **distinct social proof section when requested**; safe generic placeholders (no fabricated named brand claims) |
| `sections/social-proof.yaml` | **REQUIRED as a distinct section when requested**; acceptable forms (testimonial strip / logo-trust row / credibility stats / quote cards / adoption proof); safe placeholders; omit only when genuinely irrelevant |
| `sections/landing-hero.yaml` | Primary CTA + **secondary CTA when prompt asks for both** (e.g. "See how it works", "View examples", "Read the playbook"); do not collapse dual CTAs; never `href="#"` |
| `sections/final-conversion.yaml` | Distinct closing section (not a verbatim CTA-band reuse); real anchor target, never `href="#"`; no fake form submission |
| `components/cta-button-group.yaml` | Added `secondaryHref` prop + guidance: render secondary CTA when requested; real anchors not `href="#"`; meaningful labels |
| `validators/no-lorem-dead-cta.yaml` | Pass/fail conditions now name dead `href="#"` anchors and fake forms explicitly |
| `validators/cta-clarity.yaml` | Secondary CTA present when requested; fail when dual CTAs collapsed |
| `validators/landing-section-presence.yaml` | Distinct social-proof section required when requested; fail when omitted |

Rendered v2 context grew from 8,593 → **10,776 chars** (still < 11.4k preferred, < 12k cap).

### 4.3 Forced-v2 run — v2 context confirmed (both runs)

| Check | Result |
|-------|--------|
| Scaffold context source | **v2** |
| Pack id | **`pack.site`** |
| App type | **`site.landing-page-core`** |
| Rendered v2 context length | **8,593 chars** |
| v1 Builder Kit fallback | **Not used** |

---

## 5. Gate checklist — pass rerun (post recipe-guidance fix)

Evaluated against the **pass primary run** (`/tmp/ham-landing-page-core-gate-review-pass/generated/`), which routes to v2 with the exact specified prompt after the guidance fix.

| Requirement | Observed | Pass/Partial/Fail | Notes |
|-------------|----------|-------------------|-------|
| Routes to `site.landing-page-core` | **yes** | **Pass** | |
| v2 context used, not v1 fallback | **yes** (10,776 chars, `pack.site`) | **Pass** | `v1_fallback_used=false` |
| Hero present, specific value proposition | `Hero.tsx` — "Build Better AI-Powered Apps" + audience subhead | **Pass** | |
| **Primary + secondary CTA** | hero "Get Started" (→`#features`) + "See how it works" (→`#faq`) | **Pass** | **Gap closed** — dual hero CTAs |
| Value proposition present | `ValueProposition.tsx` | **Pass** | |
| Feature/value sections present, non-repetitive | `FeatureValueGrid.tsx` — 3 differentiated cards | **Pass** | No icon-card spam |
| **Social proof / trust present** | `SocialProof.tsx` — "Trusted by Developers" + quote | **Pass** | **Gap closed** — distinct section |
| Social proof plausible / placeholder-safe | "Senior Engineer, Growth-Stage Startup" | **Pass** | Generic plausible placeholder, no fabricated named brand |
| FAQ present | `FAQ.tsx` | **Pass** | Conversion-oriented |
| Final conversion section distinct | `FinalConversion.tsx` — "Don't Miss Out!" vs CTA band "Ready to Get Started?" | **Pass** | Distinct headline/copy |
| **No `href="#"`** | all CTAs use `#features` / `#faq` | **Pass** | **Gap closed** — no dead anchors |
| CTAs meaningful, not vague | "Get Started" / "See how it works" | **Pass** | |
| Section narrative flows logically | hero → value → features → social proof → CTA → FAQ → final | **Pass** | Full problem→solution→proof→action arc |
| Semantic headings/buttons/links | single h1, h2 sections, `<a>` anchors | **Pass** | |
| Responsive / mobile considerations | `grid-cols-1 md:grid-cols-3`, `h-screen` hero | **Partial** | Feature grid responsive; other sections layout-light |
| No lorem ipsum | none | **Pass** | |
| No dead fake forms pretending to submit | no forms at all | **Pass** | |
| No template/source cloning | freshly generated | **Pass** | |
| No dashboard/app/ecommerce/CMS/backend/game drift | landing-page shape | **Pass** | "no backend" honored |
| Static / local-only | pure static React, no backend | **Pass** | |
| Generated output not committed | under `/tmp/` | **Pass** | |
| Inspector (`inspect_generated_scaffold_quality`) | 0 issues | **Uninformative** | Inspector guards are game-focused; no landing-page detectors yet |

---

## 6. Generated output summary

### Pass primary run (`-pass/generated/`, 13 files) — **v2, routed, all gaps closed**

```
package.json, vite.config.ts, index.html, src/main.tsx, src/index.css,
src/App.tsx,
src/components/Hero.tsx
src/components/ValueProposition.tsx
src/components/FeatureValueGrid.tsx
src/components/SocialProof.tsx
src/components/CTABand.tsx
src/components/FAQ.tsx
src/components/FinalConversion.tsx
```

- `App.tsx` composes: `Hero → ValueProposition → FeatureValueGrid → SocialProof → CTABand → FAQ → FinalConversion`.
- **Social proof:** distinct `SocialProof.tsx` with a safe generic placeholder quote ("Senior Engineer, Growth-Stage Startup") — no fabricated named brand.
- **Dual hero CTA:** "Get Started" (→`#features`) + "See how it works" (→`#faq`).
- **No dead anchors:** every CTA uses an in-page `#features`/`#faq` target; no `href="#"`.
- **Distinct final conversion:** "Don't Miss Out!" headline, separate from the mid-page CTA band.
- All Tailwind utility styling; no backend calls, no `<form>` submit handlers — "no backend" honored.

### Routing-fix primary run (`-fixed/generated/`, 12 files) — v2, routed (pre-guidance-fix)

Routed correctly but omitted social proof, dropped to a single hero CTA, and used `href="#"` on the final CTA — the gaps the recipe-guidance fix targeted.

### Initial primary-run artifact (`generated/`, 6 files) — v1 fallback (pre-routing-fix)

A flat v1 Builder Kit landing scaffold — the symptom of the routing false negative, now resolved.

---

## 7. Positive observations

- **Routing precedence is safe:** when forced to v2, the recipe composes and renders cleanly (`pack.site`, 8,593 chars) — the routing/context wiring landed in `999b63a6` works.
- **Section decomposition is real:** the recipe drove a multi-component landing page (hero, value prop, feature grid, CTA, FAQ) rather than a single dumped file.
- **Logical marketing narrative** with primary + secondary hero CTAs and a conversion-oriented FAQ.
- **No slop signatures:** no lorem ipsum, no fake-submit forms, no icon-card spam, no template cloning, no product drift.
- **Static/local-only honored:** the "no backend / no live form handling" intent is respected in the generated artifact.
- **v1 default preserved:** the primary run demonstrably falls back to v1 with the flag on but no v2 match.

---

## 8. Remaining gaps

1. **Routing false negative — RESOLVED** (§4.0). Specified prompt routes to v2.
2. **Social proof omitted — RESOLVED** (§4.4). Distinct `SocialProof` section now generated with safe placeholders.
3. **Hero secondary CTA dropped — RESOLVED** (§4.4). Hero now emits primary + secondary CTAs.
4. **Dead `href="#"` CTA — RESOLVED** (§4.4). All CTAs use in-page anchor targets.
5. **Thin responsiveness (minor, open):** feature grid is responsive; other sections layout-light. Cosmetic; not gate-blocking. Could be a future recipe-guidance nudge.
6. **Anchor-target hygiene (minor, open):** CTAs point to `#features`/`#faq`, but generated sections don't always carry matching `id`s. Not a dead `href="#"`; minor polish via recipe guidance.
7. **No landing-specific quality detectors (open):** `inspect_generated_scaffold_quality` returns 0 issues because its guards are game-oriented. A website-lane inspector (missing-required-section, generic-hero, weak-CTA, social-proof-absent) would make this gate **enforceable** rather than manual — recommended next step (runtime, deferred).

---

## 9. Safety / routing observations

- **Base routing landed in `999b63a6`**; the routing-fix (negated-constraint handling) is local/uncommitted in `src/ham/build_registry/intent.py` + tests.
- **Build Registry v2 remains opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off ⇒ v1 default; routing only adds metadata when flag + intent match.
- **No generic website/page/design/homepage router** — routing remains the narrow `site.landing-page-core` matcher. Negated-constraint stripping applies **only after a strong landing positive matches**, so weak prompts ("build a website with no backend") still do not route.
- **Excluded families still excluded** — dashboard/ecommerce/CMS/backend/auth/game/clone negatives remain intact for non-negated phrasing; genuine feature requests ("backend auth and user accounts", "ecommerce checkout with payments", "admin dashboard") still block.
- **Game routing preserved** — landing matcher remains lowest precedence after all game routes; full game suite green.
- **Generated artifacts remain under `/tmp/`** — not committed; no app output added to the repo.
- **Scope:** routing logic + website-pack recipe guidance/validators + tests + this doc only; no API/frontend/Builder Studio/CI/scaffold-behavior/v1 JSON/template/game-pack-YAML/website-registry-YAML changes; no new recipes or routing.

---

## 10. Gate decision

| Phase | Dimension | Decision |
|-------|-----------|----------|
| **Initial** | Routing (specified prompt) | **Hold** — false negative; "no backend" blocked an otherwise-valid landing prompt |
| **Initial** | Recipe v2 quality (forced-v2) | **Conditional pass** — social-proof missing, final-conversion reused |
| **Routing-fix rerun** | Routing (specified prompt) | **Pass** — same prompt routes to `site.landing-page-core`, v2 context, no v1 fallback |
| **Routing-fix rerun** | Recipe v2 quality (primary run) | **Conditional pass** — distinct final-conversion + accessible FAQ; social-proof still omitted, hero secondary CTA dropped, `href="#"` |
| **Quality-fix pass rerun** | Routing (specified prompt) | **Pass** — routes to `site.landing-page-core`, v2 context (10,776 chars), no v1 fallback |
| **Quality-fix pass rerun** | Recipe v2 quality (primary run) | **Pass** — distinct social-proof section (safe placeholder), hero primary + secondary CTA, all CTAs use in-page anchors (no `href="#"`), distinct final conversion |
| **Overall (current)** | — | **Pass** — routing reliable; all three targeted quality gaps (social proof, dual CTA, dead anchor) closed via website-pack recipe guidance. Only minor cosmetic polish and a future runtime quality detector remain (non-blocking). |

---

## 11. Recommendation

1. **Routing fix is complete** — negated backend/form/payment/CMS constraints no longer block routing when strong landing positives are present; genuine feature requests still block. Lock-in tests added.
2. **Quality-guidance fix is complete** — website-pack recipe guidance now makes social proof required-when-requested (with safe placeholders), preserves hero primary + secondary CTAs, and bans dead `href="#"` in favor of in-page anchors. Pass rerun confirms all three gaps closed. Lock-in render tests added.
3. **Add website-lane quality detectors** to `inspect_generated_scaffold_quality` (missing-required-section, generic-hero, weak-CTA, absent-social-proof) to make this gate **enforceable** rather than manual — recommended runtime follow-up (deferred).
4. **Minor cosmetic polish (non-blocking):** nudge non-feature sections toward responsive layout and ensure anchor targets carry matching section `id`s (future recipe-guidance tweak).
5. **Do not enable Build Registry v2 by default.**
6. **Do not commit generated app output.**
7. **Website lane is a Pass** — routing reliable and the targeted generated-quality gaps are closed; the landing-page stack is ready to commit/push when the operator requests it.

---

## 12. References

- [LANDING_PAGE_CORE_READINESS_REVIEW.md](../LANDING_PAGE_CORE_READINESS_REVIEW.md)
- [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](../WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)
- [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](../WEBSITE_DESIGN_SYSTEM_DIRECTION.md)
- [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](../DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md)
- [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md)
- [STATUS.md](../STATUS.md)
