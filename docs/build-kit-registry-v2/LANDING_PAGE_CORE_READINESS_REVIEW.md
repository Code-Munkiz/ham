# Landing Page Core Readiness Review

> **Readiness/ambiguity gate only · Not recipe approval · Not routing approval · Not implementation authorization**

Ambiguity and routing-risk review before authoring a potential **`site.landing-page-core`** website/design-system Build Registry v2 recipe. This document evaluates prompt boundaries, scope limits, generated-quality expectations, and sibling-lane collisions. It does **not** add a recipe, routing, templates, starter source files, or runtime changes.

**Review date:** 2026-05-27 (UTC)  
**Baseline:** `origin/main` at `ab1351b1` — sixteen game recipes, 376 indexed modules (Game Pack), all game recipes routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`, reference checker **0 errors / 0 warnings**. Website direction and design doctrine landed; **no website recipes yet**.

For workstream direction see [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md). For design doctrine see [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md). For routing policy see [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md).

---

## 1. Executive summary

**`site.landing-page-core` is the recommended first website/design-system recipe.**

It is attractive because it is **bounded**, **common** (hero → sections → CTA), and **useful** as a generative playbook without backend, payments, or CMS complexity.

**It should be authored schema-only first.** Routing, scaffold quality guard extensions, and generated gate reviews come **after** separate human approval — not in the same step as schema land.

**This review does not add a recipe, routing, templates, or implementation.**

**Recommended posture if website kits proceed:** decide **`website-pack/`** file structure → author **`site.landing-page-core` YAML only** → validate/compose/render/reference-check → **defer routing** until explicit approval per [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) → run **`/tmp/` generated gate review** before declaring the recipe complete.

---

## 2. Current baseline

| Dimension | State |
|-----------|--------|
| **DOM-native game-kit phase** | **Complete** — see [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md) |
| **Game recipes (Game Pack)** | 16 |
| **Indexed modules (Game Pack)** | 376 |
| **Game routing** | All sixteen game recipes route narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | v1 Builder Kit JSON when flag off |
| **Reference checker** | `scripts/check_build_registry_references.py` — **0 errors, 0 warnings**; local/manual; not CI-blocking |
| **Website direction doc** | [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md) — landed |
| **Website design doctrine** | [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) — landed |
| **Website recipes** | **None yet** |
| **Website routing** | **None yet** |
| **Templates / starter files** | None — generative playbooks only |
| **Public kit picker / default v2** | None |

---

## 3. Candidate lane intent

Safe intended shape for **`site.landing-page-core`** (schema authoring target — **not yet implemented**):

| Area | Intended behavior |
|------|-------------------|
| **Platform** | DOM-native, static, single-page marketing/landing surface (React/Vite-style) |
| **Hero** | Clear headline, supporting subhead, primary CTA (and optional secondary) |
| **Value proposition** | Problem/solution framing — why the offer matters |
| **Feature / value sections** | 2–4 structured blocks with hierarchy — not undifferentiated icon-card rows |
| **Trust / social proof** | Testimonials, logos, stats, or credibility strip — plausible placeholder copy OK |
| **CTA section** | Repeated conversion block with meaningful label tied to the offer |
| **FAQ or final conversion** | Optional FAQ accordion or closing CTA supporting conversion |
| **Responsive layout** | Mobile-friendly stacking; no desktop-only fixed-width traps |
| **Accessibility basics** | Semantic headings, labeled buttons/links, contrast-aware sections |
| **Visual hierarchy** | Consistent type scale, spacing rhythm, CTA emphasis — see [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) |
| **Backend** | **Not required** — no auth, API, database, or live form submission |
| **Out of scope** | Payments, CMS, multi-page app routing, dashboard logic, ecommerce checkout |

---

## 4. Why this is the right first website lane

| Factor | Rationale |
|--------|-----------|
| **Bounded enough to test** | One page, 5–7 sections, static content — fits render budget and gate checklist |
| **Common user request** | “Landing page”, “marketing site”, “product page with hero and features” appears frequently in builder prompts |
| **Teaches section rhythm** | Forces narrative arc (problem → solution → proof → action) and visual hierarchy doctrine |
| **Foundation for siblings** | Natural precursor to `site.marketing-site-multi-section` and bounded `site.saas-product-page` lanes |
| **Lower risk than deferred lanes** | Dashboards, ecommerce, CMS/docs, and app-like surfaces overlap product-building and game routing |
| **Parallel to game-kit rhythm** | Schema-first + readiness + generated gate proved the model for sixteen game recipes |
| **Reference checker headroom** | Game siblings post-trim sit ~8.8k–11.0k chars; a disciplined landing playbook can target **under 11.4k** (90% of 12k cap) |

---

## 5. Why this is risky

| Risk | Detail |
|------|--------|
| **Generic AI-slop hero** | Centered headline + “Get started” with no specific value proposition |
| **Vague copy** | “Revolutionize your workflow”, “Next-gen platform” without audience or offer |
| **Icon-card spam** | Three identical feature cards with emoji icons and one-line blurbs |
| **Inconsistent spacing / typography** | Random padding; mixed heading sizes with no scale |
| **Weak CTA hierarchy** | Multiple equal-weight buttons; dead or generic CTAs |
| **Fake dashboard screenshots** | Decorative app chrome with no narrative purpose |
| **Mobile layout ignored** | Fixed widths, overflow, tiny tap targets |
| **Lorem ipsum** | Placeholder text without structure — non-reviewable output |
| **Template-like sameness** | Inter + purple gradient + three cards — indistinguishable AI default |
| **Brandless SaaS aesthetic** | No coherent tokens; every section looks like a different template |
| **Routing ambiguity** | Weak terms (“website”, “homepage”, “SaaS”) could steal app/dashboard/game prompts if routing is too broad |
| **Form/backend creep** | Waitlist/email capture can drift into auth, API, and validation logic |

---

## 6. Ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Generic website / homepage** | “build a website”, “make a homepage”, “modern page” | **Weak signal — no route alone**; v1 fallback |
| **Marketing site multi-section** | “long marketing page”, “multi-section landing”, “scroll marketing site” | **Possible sibling / future lane** (`site.marketing-site-multi-section`); do not collapse into landing-core without section checklist |
| **SaaS product page** | “SaaS landing”, “product page with pricing table”, “feature comparison” | **Possible sibling / future lane**; pricing-table prompts need explicit signals — not landing-core default |
| **Waitlist / launch page** | “coming soon”, “waitlist page”, “launch page with email signup” | **Possible sibling / future lane** if form scope stays static placeholder; **do not route** live capture to landing-core |
| **Portfolio / showcase** | “portfolio site”, “case study grid”, “showcase my work” | **Separate future lane** — image/project grid semantics differ |
| **Dashboard / app UI** | “dashboard”, “admin panel”, “metrics app”, “CRM UI” | **Do not route to landing page** — overlaps product builder and `game.resource-management-sim` negatives |
| **Ecommerce / storefront** | “online store”, “shop page”, “checkout”, “cart” | **Defer** — payments, catalog, cart state |
| **Docs / CMS / blog** | “documentation site”, “blog”, “CMS”, “help center” | **Separate future lane** — nav, search, multi-page content |
| **Auth / payments / forms / backend** | “login”, “signup”, “Stripe checkout”, “contact form that saves to DB” | **Out of scope** for landing-core |
| **Game / app build requests** | “build a game”, “todo app”, “chat app”, “city builder” | **Preserve existing game/app handling** — game recipes and v1 kits; never route to `site.*` |

---

## 7. Strong positive signals for future routing

Future **`site.landing-page-core`** routing (when approved) should require **combined** signals, not single keywords:

| Signal cluster | Examples |
|----------------|----------|
| **Landing / marketing page** | “landing page”, “marketing page”, “conversion page”, “product landing page” |
| **Hero + value** | “hero section”, “value proposition”, “headline and subhead”, “above the fold” |
| **CTA** | “call to action”, “sign up button”, “book a demo”, “start free trial” (copy-level — still static) |
| **Feature sections** | “features section”, “benefits section”, “how it works” (2–4 blocks) |
| **Social proof** | “testimonials”, “customer logos”, “social proof”, “trust strip”, “stats bar” |
| **FAQ / close** | “FAQ section”, “frequently asked questions”, “final CTA”, “closing conversion block” |
| **Responsive marketing** | “responsive landing page”, “mobile-friendly marketing page”, “single-page marketing site” |
| **Launch / waitlist (bounded)** | “launch page”, “coming soon page” **only if** prompt also describes static marketing sections without live backend |

**Conservative rule:** require **hero + (features or value prop) + CTA** language before positive match. Single term “landing page” alone is insufficient if prompt is clearly an app, dashboard, or game.

---

## 8. Weak signals that should not route alone

These terms are **insufficient** for routing without strong landing-section signals and explicit negative-pattern passes:

| Weak term | Why insufficient |
|-----------|------------------|
| **website** | Could mean app, blog, store, or dashboard |
| **homepage** | Could mean app shell or CMS home |
| **page** | Universal — no lane specificity |
| **design** | Visual polish request, not landing archetype |
| **modern** | Style adjective only |
| **SaaS** | Often means full product UI, auth, billing |
| **startup** | Brand/context, not structure |
| **product** | Could mean dashboard, inventory, or game |
| **beautiful** | Aesthetic only |
| **responsive** | Layout constraint, not page type |
| **dashboard** | App surface — explicit exclusion |
| **app** | Application build — route to v1 or game lanes |

When in doubt, **do not route** — preserve v1 default per [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md).

---

## 9. Explicit exclusions

Do **not** treat these as `site.landing-page-core` (negative patterns for future routing):

| Exclusion | Rationale |
|-----------|-----------|
| **Dashboard app** | Metrics, tables, charts — app semantics |
| **Admin panel** | CRUD, roles, settings |
| **Ecommerce checkout / store** | Cart, catalog, payments |
| **Blog / CMS / docs system** | Multi-page content, nav trees, search |
| **Backend / API / auth / accounts** | Server logic out of scope |
| **Payment flows** | Stripe, checkout, subscriptions |
| **Multi-page app** | Routing, nested routes, SPA app shell |
| **Game request** | Sixteen game recipes + v1 game kits |
| **Data dashboard** | Analytics, KPI tiles, live data |
| **CRM / project management UI** | App workflows, not marketing conversion |
| **Template cloning** | “Clone stripe.com”, “copy Apple landing page pixel-perfect” |
| **Pixel-perfect clone of named site** | Legal/quality risk; not generative playbook intent |

---

## 10. Candidate scope recommendation

| Dimension | Recommendation |
|-----------|----------------|
| **Page count** | **One page** only |
| **Content** | **Static** — no live data fetching beyond optional placeholder images |
| **Sections** | **5–7 max** — hero, value, features (1–2 blocks), proof, CTA, optional FAQ |
| **Copy** | **Meaningful placeholder copy** — product/audience-specific structure; **no lorem ipsum** |
| **CTAs** | **One primary** + optional **secondary** (de-emphasized) |
| **Layout** | **Responsive** — mobile stack, readable type scale |
| **Accessibility** | Semantic headings, labeled buttons/links, contrast targets |
| **Forms** | **No live form handling** — static buttons/links only unless prompt explicitly scopes placeholder UI |
| **Backend** | **None** |
| **Payments** | **None** |
| **CMS** | **None** |
| **Dashboard logic** | **None** |
| **Multi-page routing** | **None** unless explicitly requested in a **future** lane |

---

## 11. Generated quality expectations

Future **`site.landing-page-core`** generated gate (after routing approval) should verify:

| Expectation | Pass signal |
|-------------|-------------|
| **Required sections present** | Hero, value/features, CTA; proof/FAQ when prompt requests |
| **Clear page narrative** | Problem → solution → proof → action — not random blocks |
| **Specific hero / value proposition** | Headline names audience or outcome — not vague revolution copy |
| **Meaningful CTA labels** | “Start free trial”, “Book a demo” — not lone “Learn more” |
| **Non-repetitive feature sections** | Distinct headings and copy per block |
| **Plausible social proof** | Structured testimonials/logos/stats — or omitted if prompt irrelevant |
| **FAQ / final CTA supports conversion** | Closing section reinforces primary action |
| **Semantic headings** | Single `h1`; logical `h2`/`h3` nesting |
| **Accessible buttons / links** | Semantic elements; not inert `div` buttons |
| **Mobile / responsive structure** | Viewport meta, flex/grid wrap, no obvious overflow traps |
| **Visual hierarchy from structure** | Type scale, section spacing, CTA emphasis in class/layout intent |
| **No lorem ipsum** | Structured placeholder copy acceptable |
| **No dead submit CTAs** | Primary actions are links or explicit handlers — not fake forms |
| **No AI-slop dominance** | §5 anti-patterns absent or documented false positives |
| **No template / source cloning** | Custom generated structure; artifacts under `/tmp/` only |

See [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) §6–§8 for doctrine alignment.

---

## 12. Suggested schema module themes

Illustrative module ids for schema authoring ( **not implemented** by this review):

| Theme | Example module ids |
|-------|-------------------|
| **Intent / scope** | `landing-page-intent`, `landing-anti-slop-guard`, `landing-copy-specificity` |
| **Sections** | `landing-hero-section`, `landing-value-proposition`, `landing-feature-section`, `landing-social-proof`, `landing-cta-section`, `landing-faq-section` |
| **Design system** | `landing-responsive-layout`, `landing-accessibility-basics`, `landing-visual-hierarchy` |
| **Components** | `components/hero-block`, `components/feature-grid`, `components/testimonial-strip`, `components/cta-band`, `components/faq-list` |
| **Validators (conceptual)** | Section presence, CTA clarity, semantic headings, responsive notes, no lorem ipsum, no dead form behavior |
| **Recovery playbooks** | Generic hero, weak CTA, section repetition, inaccessible buttons, mobile layout ignored |

Validators remain **`runner: conceptual`** until a separate implementation decision — same posture as game pack today.

---

## 13. Readiness decision

| Decision | Status |
|----------|--------|
| **Ready to author schema-only next?** | **Yes** — if scope remains one-page/static and routing stays deferred |
| **Routing in same step?** | **No** — routing must not land with schema |
| **Generated gate required?** | **Yes** — after future routing approval, before recipe declared complete |
| **Dashboards / ecommerce / CMS / backend** | **Deferred** |

**This review authorizes readiness documentation only.** It does **not** authorize YAML land, routing PR, or scaffold changes.

---

## 14. Recommended next step

1. **Decide initial website pack / file structure** (see §15).
2. **Author `site.landing-page-core` schema-only** under approved pack layout.
3. **Keep composed render under 12k** — preferably **under 11.4k** (90% threshold).
4. **Validate / reference-check** — `validate_game_pack_registry.py` pattern + orphan/render-budget pass when checker extended.
5. **Do not route** until explicit human approval per [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md).
6. **Add conservative routing** only after dedicated tests (`test_build_registry_intent.py` pattern) and negative patterns from §8–§9.
7. **Run generated gate review** (`/tmp/` artifact + outcome report) before declaring recipe complete.

---

## 15. Pack structure question

| Option | Assessment |
|--------|------------|
| **New `website-pack/`** under `docs/build-kit-registry-v2/website-pack/` | **Recommended** — separates website design modules from game mechanics; clearer docs and routing namespaces (`site.*` vs `game.*`) |
| **Extend `game-pack/`** | **Not recommended** — mixes unrelated module graphs; increases reference-checker and authoring confusion |

**Recommendation:**

- Create a **separate `website-pack`** with its own `registry-pack.yaml` (or equivalent) when schema authoring begins.
- **Do not restructure** existing `game-pack/` in this review.
- **Reference-checker extension** for website-pack is a **later implementation concern** — document module ids consistently at authoring time.

Open decision for schema land: recipe id prefix **`site.landing-page-core`** vs **`web.landing-page-core`** — prefer **`site.*`** per [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md).

---

## 16. Non-goals

This review does **not** authorize or imply:

- A website recipe from this document alone
- Routing changes from this document alone
- Templates or starter source files
- Backend, live forms, payments, or CMS
- Dashboard or app UI kits
- Ecommerce lanes
- CI workflow changes
- Runtime, API, frontend, or Builder Studio changes
- Scaffold quality guard extensions (until first generated gate identifies gaps)
- Committing generated app output

---

## 17. References

| Document | Relevance |
|----------|-----------|
| [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md) | Workstream direction; first lane; validation posture |
| [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) | Design doctrine; anti-patterns; gate criteria |
| [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md) | Game-kit closeout baseline |
| [GAMEPLAY_QUALITY_PRINCIPLES.md](./GAMEPLAY_QUALITY_PRINCIPLES.md) | Parallel readiness/gate pattern for game kits |
| [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) | Route-after-approval policy |
| [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md) | Recipe YAML authoring rules |
| [STATUS.md](./STATUS.md) | Live registry status |

**Related readiness pattern:** [TACTICS_GRID_AMBIGUITY_REVIEW.md](./TACTICS_GRID_AMBIGUITY_REVIEW.md) — game-kit ambiguity gate template.
