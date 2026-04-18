# Ham — Product Direction

**Status:** Non-binding direction doc. This file captures *intent and principles*, not shipped reality or committed engineering sequence. For what is actually shipped, see `VISION.md`. For what is deferred, see `GAPS.md`.

**Last updated:** 2026-04-17

## What Ham is becoming

Ham is evolving from a **local CLI** with a **bounded inspection-oriented runtime**—registry seams for profiles and backends, structured **run history** under `.ham/runs/`—toward a product that stays honest about what ran and what was reviewed.

**Near term**, the direction is a **small shared workspace** (on the order of **3–5 people**) with a **Vercel-hosted frontend**: **read-only UI first**, while **execution remains CLI-driven** on each developer’s machine. A hosted execution path may follow, but is not committed.

**Longer term**, the same design space may grow toward **configurable AI workers and subagents** with **personas**, **teams**, **plugins**, and **pluggable backends**, and **may eventually support a multi-tenant SaaS control plane**. None of that is committed; it only informs how near-term seams (registries, run records, separation of duties) should stay shaped.

## Target architecture (eventual)

- **Frontend:** Next.js (TypeScript) on Vercel.
- **Backend:** Containerized FastAPI on GCP Cloud Run.
- **Persistence target:** Firestore for structured run records and registry data.
- **Identity:** Shared API key in the small-group phase; Firebase Auth or equivalent at SaaS scale.
- **Registries:** Target surface includes personas, agents, teams, plugins, backends, and intent profiles; **today only intent profiles and backends exist** in the repo.
- **Observability:** Run history is the source of truth; progression-style metrics are **derived from runs**, not stored on registry records.
- **Monetization:** Conventional SaaS (subscriptions, paid templates, etc.); **not** crypto- or NFT-based.

## Shared workspace shape (near-term)

**Everyone sees everything by default**—no tenant isolation is required for the first shared-workspace iteration.

Access is **via a shared API key**; an **author** (or similar) field on records supports **attribution**, not access control. The **frontend reads** run history and registry-oriented data; **execution stays on the CLI** locally. A hosted execution path on Cloud Run or equivalent may follow; it is not committed.

## Principles that should survive any slice

- **Registry records are pure data:** stable `id`, `version`, `metadata` dict; **no behavior** on record types; **derived metrics live elsewhere** (see `.cursor/rules/registry-record-conventions.mdc` and run history). This applies to **registry-layer** records; **not all persisted artifacts** necessarily share the **same field schema** (run JSON under `.ham/runs/` is a different shape on purpose).
- **Honest progression only:** anything shown as “progress” must **trace to queries over real run history**—no vanity counters, fake levels, or implied “the agent got smarter” without evidence in runs.
- **No crypto primitives:** NFTs, on-chain ownership, token-gating—**out of scope**. If provenance matters later, **detached signatures over canonical JSON** are enough.
- **Hermes / Bridge / Droid separation preserved:** Hermes supervises and reviews; Bridge validates and routes bounded execution; Droid executes; **no role collapse** (see `VISION.md`).
- **Bounded execution, audit-friendly outputs:** each run produces a **structured, queryable record**.
- **Minimal diff per slice:** small, reversible, testable changes; **no framework sprawl**.
- **Build abstractions with the second use:** protocols and registries land in the **same slice** as a **second real implementation**, not preemptively.

## Gamification — how it maps honestly

RPG- or character-sheet-style UX is a **plausible** long-term presentation layer. If it ships, **class or archetype** maps to **persona**, **loadout or equipment** to **plugins**, **party** to **team**, and **level** to a **derived view over run history**. No RPG stats (XP, level, rank, badges, STR/DEX/WIS) belong **on registry records**; they are **rendered from queries over runs**. That separation is what keeps progression honest.

## What this doc is NOT

- **Not a roadmap.** Phases, sequencing, and priorities live in conversation and commit history—not here.
- **Not architecture.** Shipped modules, wiring, and status live in `VISION.md`.
- **Not a commitment.** Any of this can change; update this file when direction shifts.
- **Not marketing.** Do not treat this as external positioning or public messaging yet.
