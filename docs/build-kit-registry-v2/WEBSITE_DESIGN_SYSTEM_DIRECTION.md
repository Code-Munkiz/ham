# Website Design-System Build Kit Direction

> **Direction/readiness gate only · Not recipe approval · Not routing approval · Not implementation authorization**

Planning checkpoint for the next Build Registry v2 workstream: **website/design-system build kits**. This document defines posture, risks, validation rhythm, and first candidate lanes after the DOM-native game-kit phase closed. It does **not** add recipes, routing, templates, starter source files, runtime changes, or default v2 enablement.

**Direction date:** 2026-05-26 (UTC)  
**Baseline:** `origin/main` at `14491a0d` — sixteen game recipes, 376 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`, reference checker **0 errors / 0 warnings**, generated game gates **Pass** where documented.

For game-kit closeout see [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md). For live registry status see [STATUS.md](STATUS.md).

---

## 1. Executive summary

**The DOM-native game-kit phase is complete.**

The next workstream is **website/design-system build kits** — generative playbooks for marketing pages, landing flows, and coherent visual systems rather than playable game loops.

**This document does not add recipes, routing, templates, or implementation.** Its goal is to define:

- How website kits differ from game kits in quality expectations
- Which lessons carry forward from sixteen game recipes
- Candidate lanes, deferrals, and a proposed first recipe id
- Validation, routing, and pack-architecture posture before any YAML lands

**Recommended first lane:** `site.landing-page-core` (bounded hero → sections → CTA flow, no backend).

---

## 2. Current baseline

| Dimension | State |
|-----------|--------|
| **Game recipes** | 16 |
| **Indexed modules (Game Pack)** | 376 |
| **Routing** | All sixteen game recipes route narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | v1 Builder Kit JSON when flag off |
| **Reference checker** | `scripts/check_build_registry_references.py` — local/manual; **0 errors, 0 warnings**; not CI-blocking |
| **Generated gate rhythm** | Established — `/tmp/` operator runs, outcome reports, scaffold quality guard extensions |
| **Gameplay doctrine** | [GAMEPLAY_QUALITY_PRINCIPLES.md](./GAMEPLAY_QUALITY_PRINCIPLES.md) |
| **Templates / starter files** | None — generative playbooks only |
| **Generated app output** | Not committed |
| **Website/design-system work** | **Begins after this direction doc** — no website recipes yet |

---

## 3. Why website/design-system kits are different from game kits

| Dimension | Game kits | Website / design-system kits |
|-----------|-----------|------------------------------|
| **Primary success metric** | Playable loop — state mutates, win/loss/restart work | Coherent visual system — hierarchy, flow, conversion clarity |
| **Quality focus** | Reducer/tick wiring, anti-no-op actions, grid/card/timer logic | Layout rhythm, typography, spacing, color/contrast, responsive behavior |
| **User expectation** | “Does it play?” | “Does it look intentional and trustworthy?” |
| **Structure** | Game state, turns, resources, result screens | Sections, narrative arc, CTAs, social proof, FAQ |
| **Accessibility** | Important (buttons, focus, keyboard) | **Critical** — headings, landmarks, contrast, link/button labels |
| **Anti-patterns** | Shell UI, no-op reducers, hardcoded deltas | Generic hero slop, icon-card spam, dead CTAs, mobile ignored |
| **Generated gates** | Inspect gameplay wiring in JS/TS output | Inspect section presence, hierarchy, CTA meaning, a11y basics |

Game kits optimize for **playable loops and state mutation**. Website kits optimize for **coherent visual systems, section composition, interaction clarity, and brand fit**. Future scaffold quality checks for website kits should target **DOM structure, section completeness, and design anti-patterns** — not turn ticks or win conditions.

---

## 4. Lessons carried forward from game kits

| Lesson | Application to website kits |
|--------|-------------------------------|
| **Doctrine docs before expansion** | Write [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) before first recipe YAML |
| **Anti-pattern taxonomy** | Document unacceptable generated UI patterns before adding detectors |
| **Schema-first / route-after-approval** | Land recipe YAML only after readiness review; routing is a separate approved PR |
| **Generated gate reviews** | Representative prompts → `/tmp/` scaffold → human + structural checks → outcome report |
| **Reference checking** | Extend checker patterns as website module count grows |
| **Render budget discipline** | Keep composed playbook context under cap; trim guidance before modules bloat |
| **No template cloning** | Recipes are playbooks; HAM does not ship checked-in starter trees |
| **Test-first acceptance** | Routing/intent tests + focused quality tests where practical before declaring Pass |

The game-kit phase proved that **routing + v2 context alone do not guarantee quality** — post-output inspection and doctrine docs closed the gap. Website kits should assume the same rhythm from day one.

---

## 5. Candidate website/design-system lanes

| Lane | Purpose | Risk | Recommended order |
|------|---------|------|-------------------|
| **landing-page-core** | Single-page marketing landing: hero, value prop, features, proof, CTA | Low — bounded scope, no backend | **1 (first)** |
| **marketing-site-multi-section** | Longer single-page or shallow multi-section marketing flow | Low–medium — section sprawl, weak narrative | **2** |
| **portfolio/showcase-site** | Project grid, case-study cards, about/contact | Medium — image-heavy, layout drift | 3 |
| **waitlist/launch-page** | Pre-launch hero + email capture placeholder | Medium — form/backend creep | 4 |
| **SaaS-product-page** | Product features, pricing table placeholder, FAQ | Medium–high — overlaps dashboards and real SaaS apps | 5 |
| **documentation/site-docs** | Docs nav, sidebar, content pages | High — CMS/navigation complexity | Defer |
| **dashboard-ui-core** | App-like metrics, tables, charts | High — steals product/dashboard prompts; app semantics | Defer |
| **ecommerce-lite** | Product grid, cart UI placeholders | High — payments, inventory, backend | Defer |

**Recommend first lane:** **`landing-page-core`** — smallest coherent website archetype with clear section checklist and conversion flow.

**Defer for now:**

- **ecommerce-lite** — payments, cart state, catalog semantics
- **dashboard-ui-core** — too app-like; overlaps existing product-building and game resource-sim routing boundaries
- **documentation/site-docs** — CMS, search, multi-page nav beyond first website wave
- Anything requiring **backend, accounts, payments, or live forms** unless explicitly scoped in a later ADR

---

## 6. Proposed first candidate

**Recommended first recipe id:** `site.landing-page-core`

**In scope:**

| Area | Expectation |
|------|-------------|
| **Hero** | Clear headline, subhead, primary CTA |
| **Problem / value proposition** | Why the product or offer matters |
| **Feature sections** | 2–4 feature blocks with hierarchy — not icon-card spam |
| **Social proof / trust** | Testimonials, logos, stats, or trust strip (placeholder copy OK if structured) |
| **CTA section** | Repeated conversion block with meaningful label |
| **FAQ or final conversion block** | Optional FAQ accordion or closing CTA |
| **Responsive layout** | Mobile-friendly stacking; no desktop-only assumptions |
| **Accessibility basics** | Semantic headings, labeled buttons/links, sufficient contrast targets |

**Out of scope (first recipe):**

- Backend, auth, databases
- Forms beyond static/placeholder unless prompt explicitly requests capture UI
- Payments, checkout, subscriptions
- CMS, blog engines, multi-route apps
- Live analytics, A/B frameworks
- Pixel-perfect brand assets from user uploads

**Alternative if first lane proves too narrow:** `site.marketing-site-multi-section` — same discipline, slightly longer section graph. Do not author both simultaneously.

---

## 7. Design quality doctrine needed

Before the first website recipe lands, create:

**[WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)** (planned — not authored by this direction doc)

It should cover:

| Topic | Why it matters |
|-------|----------------|
| **Visual hierarchy** | Headline → subhead → body → CTA reading order |
| **Typography** | Scale, weight, line length, heading levels |
| **Spacing rhythm** | Consistent section padding, grid gaps, vertical flow |
| **Color / contrast** | Readable text, button states, not gradient soup |
| **Responsive behavior** | Breakpoints, touch targets, no horizontal scroll traps |
| **Accessibility** | Landmarks, focus, alt text hooks, aria labels |
| **Section composition** | Narrative arc — problem → solution → proof → action |
| **CTA clarity** | One primary action per viewport; no dead buttons |
| **Content density** | Enough copy to convert; not lorem-wall or empty shells |
| **Brand consistency** | Repeated tokens (radius, shadow, type scale) |
| **Anti-slop patterns** | Generic AI landing page tropes to reject in gates |

Parallel role to [GAMEPLAY_QUALITY_PRINCIPLES.md](./GAMEPLAY_QUALITY_PRINCIPLES.md) — persistent doctrine, not runtime config.

---

## 8. Website anti-pattern taxonomy

Unacceptable patterns for future generated gates and doctrine:

| Anti-pattern | Signal |
|--------------|--------|
| **Generic centered hero with vague CTA** | “Get started” / “Learn more” with no value prop |
| **Excessive gradients / glassmorphism** | Visual noise without hierarchy |
| **Icon-card spam** | Three identical cards with emoji icons and one-line blurbs |
| **Inconsistent spacing** | Random padding between sections |
| **Inconsistent typography** | Mixed heading sizes with no scale |
| **Weak contrast** | Light gray on white body text |
| **Inaccessible buttons/links** | Missing labels, div-onClick, no focus styles |
| **Fake dashboards / screenshots** | Decorative UI chrome with no narrative purpose |
| **Dead CTAs** | Buttons with no href, onClick, or anchor target |
| **Repeated sections with no narrative** | Same block copy-pasted without flow |
| **Mobile layout ignored** | Fixed widths, overflow, tiny tap targets |
| **Lorem ipsum / vague copy** | Placeholder text without structure |
| **Component soup without conversion flow** | Many UI primitives, no page story |

These differ from game anti-patterns (no-op reducers, hardcoded ticks). Website detectors should live in a **separate quality family** — extend `scaffold_quality.py` only after doctrine and first gate review identify repeatable signals.

---

## 9. Generated gate criteria for website kits

Future website generated gates should verify:

| Check | Pass signal |
|-------|-------------|
| **Correct route / kit selection** | Prompt maps to intended `site.*` app type when flag on |
| **v2 context used** | Build Kit Registry v2 playbook injected; v1 fallback not used on match |
| **Required sections present** | Hero, value, features, proof/trust, CTA (per recipe) |
| **Visual hierarchy from DOM** | `h1` → `h2`/`h3` structure; section landmarks |
| **CTA(s) present and meaningful** | Primary action with specific label tied to offer |
| **Responsive / mobile considerations** | Media queries, flex/grid wrap, viewport meta |
| **Accessible headings / buttons / links** | Semantic elements, aria where needed |
| **No excluded semantic drift** | Not a game loop, not a dashboard app, not ecommerce checkout |
| **No template / source cloning** | Custom generated structure, not copied starter tree |
| **No generated app output committed** | Artifacts under `/tmp/` only |

Game-specific checks (win/loss, reducer dispatch, grid ticks) do **not** apply. Website gates may later add **structural HTML/CSS heuristics** and optional Playwright accessibility snapshots — not pixel diff.

---

## 10. Validation posture

| Phase | Recommendation |
|-------|----------------|
| **Start** | Static doc + schema checks — validate YAML, compose, render length |
| **Reference checker** | Adopt game-pack checker **pattern** when website pack module count warrants it |
| **Generated review** | Manual operator gate first — representative prompts, `/tmp/` output, outcome report |
| **DOM / a11y automation** | **Later** — Playwright or ARIA snapshot checks for structure and landmarks |
| **Visual regression** | **Defer** — no pixel-perfect screenshot gates initially |
| **CI** | **No blocking** website gates in CI at first — mirror game pack warning-only posture |
| **Scaffold quality repair** | Evaluate after first gate review; preserve `HAM_SCAFFOLD_QUALITY_REPAIR=false` option |

Website validation emphasizes **structure and doctrine compliance** before automated visual scoring.

---

## 11. Routing posture

**No routing from this document.**

Future website recipes must follow [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) **route-after-approval** discipline:

| Rule | Rationale |
|------|-----------|
| **Weak terms alone must not route** | “website,” “landing page,” “homepage,” “page,” “design,” “SaaS,” “dashboard” — insufficient without lane-specific signals |
| **Preserve game routing** | Sixteen game recipes keep existing narrow matchers |
| **Website lanes must not steal app prompts** | Product builders, dashboards, admin panels, game requests, and resource-sim prompts must not collapse into generic `site.*` |
| **Negative patterns required** | Block game, dashboard, ecommerce checkout, CMS, and builder-app vocabulary before positive website match |
| **Flag-gated only** | `HAM_BUILD_REGISTRY_V2_ENABLED` remains off by default |
| **Tests before merge** | Intent selector + metadata enrichment + smoke coverage |

Website routing is **higher ambiguity risk** than game routing — conservative negatives are mandatory.

---

## 12. Pack architecture question

Two viable models:

| Model | Pros | Cons |
|-------|------|------|
| **New lane inside Build Registry v2** (e.g. `site-pack/` alongside `game-pack/`) | Shared tooling (loader, compose, render, intent); one registry story | Risk of conflating game and site modules in docs and routing |
| **Separate website-pack registry** | Clear separation; independent evolution | Duplicate tooling or adapter layer |

**Recommendation:** Start as a **clearly separated docs/design lane under Build Registry v2 planning** — mirror game-pack folder conventions in documentation and readiness reviews, but **decide final file structure (`site-pack/` vs nested lane) before authoring first recipe YAML**.

Open decisions for readiness review:

- Recipe id prefix: `site.*` vs `web.*`
- Shared stack modules vs site-only modules
- Render budget cap (same 12k default or site-specific)
- Whether website recipes reuse any cross-cutting “stack” kit entries from game pack (likely minimal)

---

## 13. Recommended next steps

1. **Create [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)** — doctrine before YAML
2. **Create `LANDING_PAGE_CORE_READINESS_REVIEW.md`** — ambiguity, routing boundaries, section checklist, deferrals
3. **Decide pack/file structure** — `site-pack/` layout, module naming, reference checker scope
4. **Author first website recipe schema-only** — `site.landing-page-core` after readiness approval
5. **Validate / reference-check** — compose, render budget, orphan pass
6. **Route only after explicit approval** — separate PR, tests, negative patterns
7. **Run generated gate review** — `/tmp/` artifact, outcome report, optional scaffold quality extension

Do **not** skip steps 1–3 to land YAML faster.

---

## 14. Non-goals

This direction document does **not** authorize or imply:

- A website recipe from this doc alone
- Routing changes from this doc alone
- Templates or starter source files
- CI workflow changes
- Runtime, API, frontend, or Builder Studio changes
- Scaffold pipeline changes (until first gate identifies gaps)
- Payments, live forms, backend, auth, or CMS work
- Pixel-perfect visual testing infrastructure
- Default v2 enablement
- Public kit picker
- Committing generated app output

---

## 15. References

| Doc | Purpose |
|-----|---------|
| [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md) | Game-kit phase closeout — baseline for this transition |
| [GAMEPLAY_QUALITY_PRINCIPLES.md](./GAMEPLAY_QUALITY_PRINCIPLES.md) | Game quality doctrine — template for website doctrine |
| [REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md](./REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md) | Reference checker pattern to extend later |
| [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) | Route-after-approval policy |
| [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md) | Recipe YAML authoring rules |
| [STATUS.md](./STATUS.md) | Live registry status and commands |
