# Website Design Quality Principles for Build Registry v2

> **Persistent doctrine · Website/design-system kit phase · Not a template · Not a recipe**

This document defines how HAM evaluates **generated website and design-system quality** for future Build Registry v2 site recipes. It complements future website recipe YAML, routing strategy, scaffold quality guards, generated gate reviews, and reference checks. It does **not** replace those mechanisms and does **not** authorize new recipes, routing, or default v2 enablement.

**Doctrine date:** 2026-05-26 (UTC)  
**Baseline:** DOM-native game-kit phase complete; **`origin/main`** at `a31812b7` — sixteen game recipes / 376 modules; website direction landed; **no website recipes or routing yet**.

For workstream direction see [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md). For game-kit closeout see [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md).

---

## 1. Purpose

Build Registry v2 recipes are **generative playbooks**, not checked-in starter sites. Quality therefore depends on what the scaffold produces under a representative prompt, not on schema validity alone.

This document provides **persistent doctrine** for:

- What “well-designed” means for generated marketing/landing sites
- Which visual and structural anti-patterns are unacceptable
- How website kit families differ in section and conversion expectations
- How generated gate reviews, tests, and future scaffold quality guards relate to one another

Use this doc when:

- Authoring or reviewing a website recipe family
- Writing readiness/ambiguity reviews before schema land (e.g. `site.landing-page-core`)
- Interpreting `/tmp/` generated gate outcomes
- Deciding whether a new website detector belongs in scaffold quality tooling

This is **not** a template, not a recipe YAML file, and not runtime configuration.

---

## 2. Current posture

| Dimension | Posture |
|-----------|---------|
| **Primary kit focus (next)** | **Website/design-system** — landing pages, marketing sections, coherent visual systems |
| **Game kit phase** | **Complete** — sixteen DOM-native game recipes; see [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md) |
| **First likely lane** | **`site.landing-page-core`** — hero → sections → CTA; no backend |
| **Website recipes** | **None yet** — doctrine and readiness before YAML |
| **Website routing** | **None yet** — route-after-approval when recipes exist |
| **Registry v2** | **Opt-in** behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | **v1** Builder Kit JSON when flag is off or unset |
| **Starter templates** | **None** — recipes remain playbooks only |
| **Reference checker** | Local/manual; **0 errors / 0 warnings** on current game pack; not CI-blocking |
| **Generated output** | Review in **`/tmp/`** before a routed website recipe is considered complete; **never commit** generated app trees |

A website recipe is not “done” when YAML validates. It is done when a **generated gate review** shows a coherent page under the canonical prompt for that family.

---

## 3. Design-system default

Prefer **reusable design tokens and section rhythm** over one-off component soup.

### Canonical model

```text
design tokens + section templates → coherent page narrative
```

- Use a **consistent type scale** (display, heading, body, caption) — not arbitrary font sizes per block.
- Use a **spacing rhythm** (section padding, grid gaps, stack spacing) — not random margins.
- Apply **accessible color/contrast** — readable text on backgrounds; visible focus states.
- Maintain **clear CTA hierarchy** — one primary action per viewport; secondary actions de-emphasized.
- Compose pages from **named sections** (hero, features, proof, FAQ, final CTA) — not disconnected widgets.

### What to avoid

- Isolated “pretty” sections with no shared tokens or narrative
- Decorative UI chrome (fake dashboards, glass panels) without communication purpose
- Generic AI-default layouts that could describe any product
- Dozens of shadcn-style primitives with no conversion story

Generated sites should feel **intentionally designed**, not **AI-default**.

---

## 4. Minimum viable website loop

Every generated marketing/landing site should satisfy this baseline unless the prompt explicitly scopes narrower (and the gate review documents the exception):

| Requirement | Expectation |
|-------------|-------------|
| **Clear intent and audience** | Headline/subhead communicate who it is for and what it offers |
| **Hero with specific value proposition** | Not vague “welcome” or “revolutionize your workflow” alone |
| **Meaningful CTA** | Primary button/link with specific label tied to the offer (e.g. “Start free trial”, “Book a demo”) |
| **Section narrative flow** | Problem → solution → proof → action — not random blocks |
| **Feature / value sections** | 2–4 structured blocks with hierarchy — not icon-card spam |
| **Trust / social proof** | Testimonials, logos, stats, or credibility strip where relevant to prompt |
| **FAQ / final CTA** | Closing conversion or FAQ when prompt requests it |
| **Responsive layout** | Mobile-friendly stacking; viewport meta; no fixed-width traps |
| **Accessible headings / buttons / links** | Semantic `h1`–`h3`, labeled controls, sufficient contrast targets |
| **No dead or fake interactions** | CTAs link or navigate; no inert primary buttons; no log-only handlers |

If any row fails on a generated gate rerun, the recipe remains **Conditional pass** or **Hold** until playbook guidance or future repair guards close the gap.

---

## 5. Visual hierarchy principles

| Principle | Guidance |
|-----------|----------|
| **Typography scale** | One display/title level, clear heading steps, readable body line length (~45–75 characters ideal) |
| **Spacing rhythm** | Consistent section vertical padding; predictable gaps between heading, body, and CTA |
| **Contrast** | Body text meets readable contrast; buttons stand out from backgrounds |
| **Content density** | Enough copy to communicate value; not wall-of-lorem or empty shells |
| **Section balance** | Alternating visual weight where helpful; avoid six identical card rows |
| **Scanning patterns** | F-pattern / Z-pattern friendly — headline first, supporting detail second, CTA visible |
| **Visual emphasis** | Primary CTA uses strongest color/weight; secondary actions visually quieter |
| **Mobile-first hierarchy** | `h1` remains singular; sections stack logically; tap targets ≥ ~44px where practical |

Hierarchy is judged from **DOM structure and CSS intent** in generated output — not pixel-perfect screenshots in early gates.

---

## 6. Anti-pattern taxonomy

These patterns are unacceptable in generated **primary page** paths. Future website inspectors may enforce a subset; all belong in doctrine regardless of detector coverage.

| Anti-pattern | Symptom | Why it fails |
|--------------|---------|--------------|
| **Generic centered hero** | Full-viewport headline + “Get started” with no specifics | No value communication |
| **Vague revolution copy** | “Revolutionize your workflow”, “Next-gen platform” without substance | Untrustworthy, non-converting |
| **Excessive gradients / glassmorphism** | Visual noise without hierarchy | Distracts from message |
| **Icon-card spam** | Three+ identical cards with emoji icons and one-line blurbs | No narrative depth |
| **Inconsistent spacing** | Random padding/margins between sections | Looks uncrafted |
| **Inconsistent typography** | Mixed heading sizes with no scale | Hard to scan |
| **Weak contrast** | Light gray on white body text | Illegible, fails a11y intent |
| **Dead CTAs** | `<button>` with no action, `href="#"`, or empty handler | Broken affordances |
| **Fake dashboards / screenshots** | Decorative app chrome with no story purpose | Misleading, adds clutter |
| **Repeated sections with no narrative** | Same block copy-pasted | No conversion arc |
| **Lorem ipsum / vague copy** | Placeholder text without structure | Non-reviewable output |
| **Inaccessible buttons / links** | `div` onClick, missing labels, no focus styles | Excludes users; fails basics |
| **Mobile layout ignored** | Horizontal scroll, tiny text, overlapping sections | Unusable on phones |
| **Component soup** | Many UI primitives, no page story | Pretty but purposeless |
| **Brandless SaaS slop** | Inter + purple gradient + three feature cards (generic template) | Indistinguishable from AI default |

Gate reviews should name the anti-pattern, cite file/DOM evidence, and map to future inspector codes when available.

---

## 7. Responsive / accessibility expectations

| Area | Expectation |
|------|-------------|
| **Semantic headings** | Single `h1`; logical `h2`/`h3` nesting per section |
| **Accessible button / link labels** | Visible text or `aria-label`; not icon-only primary CTAs without labels |
| **Keyboard-safe navigation** | Focusable interactive elements; visible focus where styles are applied |
| **Readable mobile layouts** | Stack columns; readable font sizes; no overflow traps |
| **Text over backgrounds** | No body text on busy images without overlay/contrast treatment |
| **Contrast-aware sections** | Dark-on-light or light-on-dark pairs chosen deliberately |
| **Small-screen layout traps** | No fixed widths that break `<768px`; touch targets not overlapping |

Accessibility is **critical** for website kits — more so than for casual game HUD labels. Early gates check **structure and labels**; automated axe/Playwright snapshots may come later (§10).

---

## 8. Generated gate criteria

Each **routed** website recipe will require a **local generated gate review** before the family is treated as complete. Reviews use existing scaffold APIs with `HAM_BUILD_REGISTRY_V2_ENABLED=true` and write artifacts only under **`/tmp/`**.

### Checklist

| Criterion | Pass expectation |
|-----------|------------------|
| **Correct kit / route selection** | Intent router returns intended `site.*` app type |
| **v2 context used** | Scaffold context source is v2; v1 fallback not used for matched prompt |
| **Required sections present** | Hero, value, features, proof/trust, CTA per recipe checklist |
| **Narrative flow exists** | Sections tell problem → solution → proof → action |
| **CTAs meaningful** | Primary action specific to offer; not dead or generic-only |
| **Headings semantic** | `h1` + section headings; landmarks where practical |
| **Mobile / responsive considerations** | Media queries, flex/grid wrap, viewport meta |
| **No anti-pattern drift** | §6 patterns absent or documented false positives |
| **No template / source cloning** | Custom generated structure; no copied starter tree |
| **Artifact hygiene** | Generated files stay local; not committed |

### Gate decisions

| Decision | Meaning |
|----------|---------|
| **Pass** | Checklist satisfied; structural/a11y review clean or documented false positives only |
| **Conditional pass** | Material improvement; known gaps remain — not production-ready claim |
| **Hold** | Shell/non-communicative page or wrong route/context — block recipe completion claim |

Generated gates are **manual/local** today — not CI-blocking (§10).

---

## 9. Test-first influence

Quality improves when tests and reviews **lead** implementation rather than chase LLM output.

1. **Readiness / ambiguity reviews** should define gate prompts, section checklists, routing exclusions, and acceptance rows **before** website recipe YAML lands ([WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md) recommends `LANDING_PAGE_CORE_READINESS_REVIEW.md` next).
2. **Observed generated failures** should become **detector + test candidates** when repeated or high-risk — mirroring `tests/test_scaffold_quality.py` growth during the game-kit phase.
3. **Tests pin intended design behavior**, not merely mirror one LLM artifact — fixtures should encode section requirements, CTA presence, and heading structure independent of a single `/tmp/` run.

Routing tests prove **prompt → recipe** discipline. Future website quality tests prove **output → coherent page** discipline. Both are required; neither replaces generated gate review.

---

## 10. Validation posture

| Phase | Recommendation |
|-------|----------------|
| **Start** | Static doc + schema checks — validate YAML, compose, render length |
| **Generated review** | Manual operator gate before declaring recipe complete |
| **Playwright / ARIA snapshots** | **Later** — DOM structure, landmarks, basic a11y signals |
| **Pixel-perfect screenshot regression** | **Defer** — structure and doctrine precede cosmetic baselines |
| **CI-blocking design gates** | **No** — mirror game pack warning-only posture initially |
| **Reference checker** | Extend checker **pattern** when site pack module count warrants it |

Website validation emphasizes **structure, narrative, and accessibility intent** before automated visual scoring or ML design judges.

---

## 11. Relationship to gameplay principles

| Aspect | [GAMEPLAY_QUALITY_PRINCIPLES.md](./GAMEPLAY_QUALITY_PRINCIPLES.md) | This document |
|--------|---------------------------------------------------------------------|---------------|
| **Primary question** | “Does it play?” | “Does it communicate and convert clearly?” |
| **Core model** | `state + action → nextState` | `tokens + sections → coherent page narrative` |
| **Success signal** | Wired controls, state mutation, win/loss/restart | Hierarchy, section flow, meaningful CTAs, a11y basics |
| **Anti-patterns** | No-op reducers, empty seeds, hardcoded ticks | Generic hero slop, dead CTAs, icon-card spam |
| **Shared rhythm** | Doctrine → readiness → schema → route approval → `/tmp/` gate → detectors | Same |
| **Shared posture** | No templates; v2 opt-in; v1 default; generated output not committed | Same |

Gameplay doctrine and website doctrine are **parallel**, not merged. Do not apply game inspectors (win/loss, reducer dispatch) to landing pages. Do not apply website section checks to tactics grids.

Both documents inform future **`scaffold_quality.py`** extensions — in **separate family branches** with family-specific repair prompts.

---

## 12. What not to overbuild yet

Explicit deferrals — do not treat absence as a gap to close in this phase:

| Deferred | Rationale |
|----------|-----------|
| **Pixel-perfect visual regression** | Structure and narrative precede screenshot baselines |
| **VLM / ML design judge** | Subjective and flaky; doctrine + human gate first |
| **CI-blocking design gates** | Local/manual gates until patterns stabilize |
| **Full design-system compiler** | Recipes are playbooks, not token pipeline products |
| **Backend / forms / payments / CMS** | Out of scope for first website wave unless explicit ADR |
| **Template cloning** | Generative custom output only; no checked-in starter trees |
| **Ecommerce / dashboard website lanes** | High ambiguity; deferred in direction doc |

Implement detectors and automation only when failures are **repeated**, **high-severity**, and **cheap to signal** without excessive false positives.

---

## 13. References

| Document | Relevance |
|----------|-----------|
| [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md) | Workstream direction, lanes, first candidate, validation/routing posture |
| [GAMEPLAY_QUALITY_PRINCIPLES.md](./GAMEPLAY_QUALITY_PRINCIPLES.md) | Parallel doctrine for DOM-native game kits |
| [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md) | Game-kit phase closeout baseline |
| [REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md](./REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md) | Reference checker pattern to extend for site pack |
| [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) | Route-after-approval discipline |
| [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md) | Recipe YAML authoring rules |
| [STATUS.md](./STATUS.md) | Live registry/routing/checker snapshot |

**Related code (read-only context — not modified by this doctrine):**

- `src/ham/scaffold_quality.py` — current inspectors target game families; website family TBD
- `src/ham/build_registry/intent.py` — game routing today; website routing TBD
- `scripts/check_build_registry_references.py` — local reference checker
