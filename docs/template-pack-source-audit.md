# Template Pack Source Audit

Internal governance for HAM Template Pack Registry v1. This document classifies
team-suggested repositories and defines how HAM may use external free/open-source
UI resources **without** exposing a template picker or ingesting unverified third-party
template marketplaces.

**Canonical machine-readable catalog:** `template-packs/sources/approved-sources.yaml`

**Product boundary:** Template packs are backstage Native Hermes workspace starters.
They are not npm library scaffolds and not user-facing template catalogs.

---

## Executive decision

The team-suggested repos are **React component-library build/scaffold tooling**, not
polished landing/dashboard UI block libraries. **Do not ingest them into
`template-packs/` as user-facing UI source.**

HAM's working strategy (proven by staging smoke on `118e12cf`):

1. Ship **HAM-authored internal packs** (`source_audit_status: ham_authored`).
2. Allow **curated copy-paste/reference** from an approved OSS UI catalog when individually verified.
3. Block commercial/aggregator template sources permanently.
4. Defer external imports until a pack moves to `verified_external` with explicit license review.

---

## Team-suggested repo classifications

| Repo | URL | Purpose | License | Polished UI blocks? | Safe for generated user projects? | Useful for HAM now? | Possible future use | Recommendation |
|------|-----|---------|---------|---------------------|-----------------------------------|---------------------|---------------------|----------------|
| **startbase-dev/tsup-template** | https://github.com/startbase-dev/tsup-template | tsup scaffold for publishing a React component library | MIT | **No** — build config + demo stubs | **Unknown** — library packaging, not app UI | **No** | Internal npm package scaffold if HAM ships reusable UI primitives | **Do not use as template pack source.** Tooling reference only. |
| **react18-tools/turborepo-template** | https://github.com/react18-tools/turborepo-template | Turborepo monorepo for React/Next library development, tests, publish CI | MIT (typical for template) | **No** — monorepo tooling + example apps | **No** for end-user previews — wrong shape (library monorepo) | **No** | Overkill even as internal scaffold; not aligned with single Vite app packs | **Reject for template packs.** Tooling only. |
| **flaviodelgrosso/react-library-builder** | https://github.com/flaviodelgrosso/react-library-builder | Rollup + Storybook starter for React libraries | MIT | **No** — Storybook button demo, not marketing/dashboard UI | **Unknown** | **No** | Storybook/Rollup reference for a future HAM design system repo | **Do not ingest.** Tooling only. |
| **mndlx/create-library** | https://github.com/mndlx/create-library | CRA-like CLI to scaffold React libraries with Vite + TS | **Unknown** (no LICENSE file detected on GitHub) | **No** — generator output is library layout | **No** until license verified | **No** | Possible internal CLI if license clarified | **Reject until license is verified.** Not a UI source. |
| **remahmoud/create-react-ts-lib** | https://github.com/remahmoud/create-react-ts-lib | CLI to create React TS libraries with Rollup | MIT | **No** — library scaffold | **Yes** as tooling output, **not** as HAM preview UI | **No** | Internal package generator only | **Do not ingest.** Tooling only. |
| **janryWang/doc-scripts** | https://github.com/janryWang/doc-scripts | React documentation site build scripts (react-scripts-like for docs) | MIT | **No** — documentation tooling | **N/A** | **No** | Docs site pipeline for a future component catalog | **Do not ingest.** Documentation tooling only. |

### Why these were suggested (and why they do not map to template packs)

These repos optimize **library authoring**: bundlers (tsup/Rollup), monorepos (Turborepo),
Storybook, publish workflows, and doc-site scripts. HAM template packs need **complete,
polished Vite app starters** with landing/dashboard sections, Tailwind visual hierarchy,
and `data-ham-section` quality gates — a different product shape.

---

## Approved external UI sources (reference/copy-paste only — not imported yet)

See `template-packs/sources/approved-sources.yaml` for the authoritative list.

| Source | Purpose | License | HAM usage (current) |
|--------|---------|---------|---------------------|
| **shadcn/ui** | Base app primitives/components | MIT | Reference for spacing, accessibility patterns; future curated import |
| **HyperUI** | Landing/marketing sections | MIT | Reference for section structure; future curated import |
| **Tremor / Tremor Blocks** | Dashboard/analytics blocks | Apache-2.0 (verify per artifact) | Reference for dashboard density; per-block review before import |
| **Tabler Icons** | Iconography | MIT | npm dependency or inline SVG |
| **Magic UI (core OSS only)** | Animated landing accents | MIT (core only) | Later, curated snippets only — **no Pro templates** |

**Import rule:** moving from reference to vendored code requires
`source_audit_status: verified_external`, `third_party_code_included: true`, explicit
`approved_ui_sources` entries, and license_notes per pack.

---

## Blocked sources (never ingest)

These must not appear in pack manifests, approved source lists, or generated user projects
as copied template source:

- Tailwind UI / Tailwind Plus
- Untitled UI
- Cruip
- Creative Tim
- Float UI
- Preline
- Aceternity Pro
- HTMLRev and other aggregator template catalogs

Enforced in code via `validate_pack_source_metadata()` and
`template-packs/sources/approved-sources.yaml`.

---

## Current HAM-authored packs (shipped)

| Pack | Status | Third-party code | Strategy |
|------|--------|------------------|----------|
| `landing/agency-modern` | `ham_authored` | `false` | HAM-authored starter inspired by approved copy-paste UI patterns |
| `landing/saas-clean` | `ham_authored` | `false` | Same |
| `dashboard/project-management` | `ham_authored` | `false` | Same |
| `dashboard/analytics` | `ham_authored` | `false` | Same |

---

## Out of scope for this audit

- Template picker UI
- User-facing template marketplace
- Native Hermes JSON artifact mode
- Cloud Tasks / Firestore / preview proxy / Workbench UI changes
- Copying HyperUI, shadcn, or Tremor code into the repo (deferred)

---

## Next steps (when approved)

1. Pick one landing pack section (e.g. hero) for a **single** HyperUI or shadcn snippet import pilot.
2. Record license + attribution in `license_notes`; set `verified_external` only for that pack.
3. Keep build-tooling repos out of `template-packs/` entirely — use them only if HAM ships a separate design-system npm workspace.
