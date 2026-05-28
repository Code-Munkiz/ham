# Landing Page Core Completion Checkpoint

Closeout checkpoint after the first **website/design-system Build Registry v2** stage completed on `origin/main`. This document **closes the `site.landing-page-core` website-pack lane** — it is **not** approval for new recipes, routing changes, runtime enablement, default v2 rollout, dashboard kits, or generated app output in the repo. For live status see [STATUS.md](STATUS.md).

**Checkpoint:** `origin/main` at `48297c4a` — **1 website recipe**, **29 indexed modules**, narrowly routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

**Latest closeout commit:** `48297c4a` — `fix(builder): close landing page generated quality gate`

---

## 1. Executive summary

**`site.landing-page-core` is complete.**

- It is the **first website/design-system Build Registry v2 recipe** — a one-page static marketing/landing playbook under `pack.site`.
- **Schema, validation, routing, and generated gate review are all landed** on `origin/main`.
- **Final gate decision: Pass** — hero dual CTA, social proof, and dead-anchor gaps closed via recipe guidance; routing false negative on negated backend constraints fixed.
- **This checkpoint adds no recipes, routing, templates, or runtime changes** — documentation only.

---

## 2. Current baseline

| Field | Value |
|-------|--------|
| **main / origin sync** | Synced at **`48297c4a`** — `fix(builder): close landing page generated quality gate` |
| **Game pack** | **Complete** — 16 recipes / **376 modules** (DOM-native phase closed; see [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md)) |
| **Website pack** | **Active** — first recipe **`site.landing-page-core`**, **29 modules** |
| **`pack.site` validation / reference checker** | Supported — `scripts/validate_game_pack_registry.py` + `scripts/check_build_registry_references.py` with `--pack` / `--pack-root` for website-pack |
| **v1 default** | Preserved — Lane A uses existing Builder Kit JSON when flag is off |
| **v2 opt-in** | **`HAM_BUILD_REGISTRY_V2_ENABLED`** must be truthy for routing metadata and v2 playbook context |
| **Templates / starter files** | **None** — generative playbooks only |
| **Generated output** | **Not committed** — gate artifacts under `/tmp/` only |
| **CI posture** | Runtime trimmed successfully earlier; latest CI loop is much healthier; reference checker remains local/manual, not CI-blocking |

---

## 3. Completed artifacts

| Artifact | Location / commit (representative) |
|----------|-------------------------------------|
| Website design system direction | [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md) — `a31812b7` |
| Website design quality principles | [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) — `8f7d022a` |
| Landing page readiness review | [LANDING_PAGE_CORE_READINESS_REVIEW.md](./LANDING_PAGE_CORE_READINESS_REVIEW.md) — `bff12d57` |
| Website pack structure plan | [WEBSITE_PACK_STRUCTURE_PLAN.md](./WEBSITE_PACK_STRUCTURE_PLAN.md) — `bcf2c39c` |
| Website-pack skeleton | [website-pack/](./website-pack/) — `ec0b258c` |
| `site.landing-page-core` schema | [website-pack/app-types/site.landing-page-core.yaml](./website-pack/app-types/site.landing-page-core.yaml) |
| `pack.site` validation / checker support | `41e00a3b` — `feat(builder): support website pack validation` |
| Landing-page routing | `ea83eb15` — `feat(builder): route landing page recipe behind registry flag` |
| Generated gate review | [outcome-reports/site.landing-page-core.gate-review.md](./outcome-reports/site.landing-page-core.gate-review.md) — `48297c4a` |

**Recent website/design-system chain (chronological):**

`a31812b7` → `8f7d022a` → `bff12d57` → `bcf2c39c` → `ec0b258c` → `41e00a3b` → `ea83eb15` → `48297c4a`

---

## 4. Landing-page recipe status

| Field | Value |
|-------|--------|
| **Recipe id** | `site.landing-page-core` |
| **Pack** | `pack.site` |
| **Module count** | 29 (1 app + 1 stack + 7 sections + 5 components + 7 validators + 6 recovery + 1 progress + 1 learning) |
| **Render / context length (post quality fix)** | **10,776 chars** (< 11.4k preferred, < 12k cap) |
| **Routing** | Behind **`HAM_BUILD_REGISTRY_V2_ENABLED`** + narrow static landing/marketing intent |
| **v1 fallback** | Preserved when flag is off or intent does not match |
| **Final gate** | **Pass** — see [site.landing-page-core.gate-review.md](./outcome-reports/site.landing-page-core.gate-review.md) |

**Composed sections (when routed):**

`section.landing-hero` → `section.value-proposition` → `section.feature-value-grid` → `section.social-proof` → `section.cta-band` → `section.faq-block` → `section.final-conversion`

---

## 5. Routing and negated-constraint fix

Conservative landing-page routing landed in **`ea83eb15`** with a follow-up negated-constraint fix in the same commit:

| Rule | Posture |
|------|---------|
| **No generic website router** | Weak signals alone (`website`, `homepage`, `page`, `design`, `modern`, `SaaS`, `startup`, `beautiful`, `responsive`) do **not** route |
| **Excluded families** | Dashboard/admin, ecommerce/payments, CMS/blog/docs, backend/auth/accounts, full web app, game, pixel-perfect clone, multi-page app (unless explicitly static marketing) do **not** route |
| **Game routing preserved** | Landing matcher runs **after** all 16 game routes — lowest precedence among matchers |
| **Negated constraints** | Phrases like **"no backend"**, **"without a backend"**, **"no live form handling"**, **"no auth"**, **"no payments"**, **"no CMS"** no longer falsely block strong landing prompts |
| **Genuine feature requests still block** | **"build a backend"**, **"with a backend"**, **"connect to an API"**, **"user accounts"**, **"payment checkout"**, **"admin dashboard"** still exclude landing routing |

Gate review caught the initial false negative (Hold → Conditional pass after routing fix → Pass after quality guidance).

---

## 6. Generated quality result

Pass rerun prompt (canonical gate):

> Build a responsive landing page for a developer tool that helps teams generate better AI-built apps. Include a specific hero value proposition, feature/value sections, social proof, clear primary and secondary CTAs, FAQ, final conversion section, accessible headings/buttons, and no backend or live form handling.

**Pass rerun artifacts:** `/tmp/ham-landing-page-core-gate-review-pass/generated/` (13 files, not committed)

| Requirement | Result |
|-------------|--------|
| Hero with specific value proposition | **Pass** — audience/outcome headline, not generic revolution copy |
| Primary + secondary CTAs | **Pass** — e.g. "Get Started" (→`#features`) + "See how it works" (→`#faq`) |
| Feature / value grid | **Pass** — differentiated cards, not icon-card spam |
| Social proof section | **Pass** — distinct `SocialProof` section with safe generic placeholder |
| FAQ | **Pass** — conversion-oriented |
| Final conversion section | **Pass** — distinct from mid-page CTA band |
| No lorem ipsum | **Pass** |
| No fake forms | **Pass** — static CTAs only; "no backend" honored |
| No `href="#"` | **Pass** — in-page anchor targets only |
| No dashboard/ecommerce/CMS/backend/game drift | **Pass** |
| Generated output location | **`/tmp/` only** — never committed |

---

## 7. Quality system lessons

| Lesson | Detail |
|--------|--------|
| **Website quality ≠ gameplay quality** | Marketing pages need section rhythm, copy specificity, CTA clarity, and trust signals — not loop/state/score detectors |
| **Design doctrine before recipe authoring** | [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md) and [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) reduced ambiguity before YAML modules were written |
| **Gate review catches what schema cannot** | Initial **Hold** exposed routing false negative; **Conditional pass** exposed omitted social proof, collapsed dual CTA, and dead `href="#"` |
| **Recipe guidance fixes generation gaps** | Strengthening section/component/validator guidance closed social proof, dual CTA, and dead-anchor issues without runtime changes |
| **Route-after-approval rhythm worked** | Readiness review → structure plan → schema land → validate/compose/render → routing commit → generated gate → quality guidance commit → outcome report → this checkpoint |

**Inspector note:** `inspect_generated_scaffold_quality()` remains game-focused and returned 0 issues for the landing gate — website-lane detectors remain a deferred follow-up, not a blocker for this stage.

---

## 8. Remaining non-blocking follow-ups

| Follow-up | Priority |
|-----------|----------|
| **Website-specific scaffold / design quality guards** | Future — missing-required-section, generic-hero, weak-CTA, absent-social-proof detectors in `inspect_generated_scaffold_quality()` or equivalent |
| **ARIA / Playwright review** | Future — accessibility automation beyond semantic-heading guidance in recipe validators |
| **STATUS / README polish** | Optional — e.g. website-pack README still mentions deferred routing in places; can align in a docs-only sweep |
| **Section `id` / anchor hygiene** | Minor cosmetic — CTAs use `#features`/`#faq` but not all sections carry matching `id`s in generated output |

**No immediate blocker** for declaring this stage complete.

---

## 9. Recommended next workstream

**Dashboard / app-surface kit research and direction next.**

Dashboards are **component-heavy**, overlap with excluded landing-page families (admin/analytics/data UI), and require **stricter gate criteria** than marketing landing pages. Do **not** author a dashboard recipe immediately without research and readiness review.

**Suggested next docs (research-first, not implementation):**

| Doc | Purpose |
|-----|---------|
| **`DASHBOARD_KIT_RESEARCH.md`** | Survey dashboard/app-surface patterns, anti-patterns, and boundary vs landing/game lanes |
| **`DASHBOARD_BUILD_KIT_DIRECTION.md`** | Design-system direction for data UI, layout contracts, and quality doctrine |
| **`DASHBOARD_CORE_READINESS_REVIEW.md`** | Readiness gate before any `app.dashboard-*` or similar schema work |

Follow the same rhythm that worked here: **direction → principles → readiness → structure plan → schema → validate → route approval → generated gate → quality guidance → checkpoint**.

---

## 10. Non-goals

This checkpoint does **not** authorize or implement:

- A new recipe from this checkpoint alone
- Routing changes from this checkpoint alone
- CI changes
- Runtime / API / frontend / Builder Studio / scaffold-behavior changes
- v1 JSON or template changes
- Recipe YAML or website/game registry YAML edits from this checkpoint
- Dashboard implementation
- Committing generated output from `/tmp/`
- Enabling Build Registry v2 by default

---

## 11. References

- [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md)
- [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)
- [LANDING_PAGE_CORE_READINESS_REVIEW.md](./LANDING_PAGE_CORE_READINESS_REVIEW.md)
- [WEBSITE_PACK_STRUCTURE_PLAN.md](./WEBSITE_PACK_STRUCTURE_PLAN.md)
- [website-pack/README.md](./website-pack/README.md)
- [outcome-reports/site.landing-page-core.gate-review.md](./outcome-reports/site.landing-page-core.gate-review.md)
- [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md)
- [STATUS.md](./STATUS.md)
