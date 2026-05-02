# HAM — Product Direction

**Status:** Non-binding direction doc. This file captures *intent and principles*, not shipped reality or committed engineering sequence. For what is actually shipped, see `VISION.md`. For what is deferred, see `GAPS.md`.

**Last updated:** 2026-05-02

## What HAM is becoming

HAM is a **HAM-native universal control surface** for directing AI workers and teams—centered on coding, building, operating, and shipping. It is **not** a thin wrapper around Hermes, Factory-style tooling, ElizaOS, OpenClaw, or any single external stack. **HAM speaks HAM internally:** one coherent product model, with **adapters and projections** to other ecosystems as a later concern, not as HAM’s primary vocabulary.

Hermes is the **main supervisory / coordinator intelligence** in the shipped pillar story; **Factory / Droid**-style patterns inform workforce and mission structure; **ElizaOS**-style patterns inform persona and character; **OpenClaw**-style patterns inform tool leverage, channels, and “soul”/memory flavor. Those systems are **reference ecosystems and inspiration**—**secondary** to HAM’s native model. **`memory_heist`** remains HAM’s **repo/workspace truth** layer (see `VISION.md`).

HAM is evolving from a **local CLI** with a **bounded inspection-oriented runtime**—registry seams for profiles and backends, structured **run history** under `.ham/runs/`—toward a **workspace / operator surface** that is **not** “just” a run-history viewer, a registry browser, or a generic admin dashboard—while staying honest about what ran and what was reviewed.

**Near term**, the direction is a **small shared workspace** (on the order of **3–5 people**) with a **Vercel-hosted frontend**: **read-only UI first**, while **execution remains CLI-driven** on each developer’s machine. A hosted execution path may follow, but is not committed.

**Longer term**, the same design space may grow toward **configurable AI workers and subagents** with **personas**, **teams**, **plugins**, and **pluggable backends**, and **may eventually support a multi-tenant SaaS control plane**. None of that is committed; it only informs how near-term seams (registries, run records, separation of duties) should stay shaped.

**Builder Platform north star (separate doc):** a fuller **aspirational** Last Mile Builder / Enterprise Orchestrator story and **phased** anchors (starting with Builder Blueprint Mode) are captured in **`docs/BUILDER_PLATFORM_NORTH_STAR.md`** so this file stays a principles lens—not a duplicate roadmap (`PRODUCT_DIRECTION` remains “not a roadmap” for sequencing prose here).

## Target architecture (eventual)

- **Frontend:** Next.js (TypeScript) on Vercel.
- **Backend:** Containerized FastAPI on GCP Cloud Run.
- **Persistence target:** Firestore for structured run records and registry data.
- **Identity:** Shared API key in the small-group phase; Firebase Auth or equivalent at SaaS scale.
- **Registries:** Target surface includes personas, agents, teams, plugins, backends, and intent profiles; **today only intent profiles and backends exist** in the repo.
- **Observability:** Run history is the source of truth; progression-style metrics are **derived from runs**, not stored on registry records.
- **Monetization:** Conventional SaaS (subscriptions, paid templates, etc.); **not** crypto- or NFT-based.
- **HAM-native agent configuration (product model):** Directionally, HAM thinks about agents through six **conceptual** concerns—**Identity** (who), **Persona** (how it thinks and communicates), **Model** (what powers it), **Tools** (what it can use), **Behavior** (how autonomous or constrained it is), **Memory** (what it remembers). This is a **canonical product-direction model**, **not** a finalized backend schema, mandatory JSON shape, or migration contract.
- **Adapters:** Future bridges to external ecosystems when useful; HAM stays **adapter-capable but not adapter-defined**. Nothing here assumes those adapters exist yet.

## Agent-first interaction (directional)

The default path is **agent-first**: the user says what they want; HAM helps configure the droid/agent/team for the job. Detailed configuration surfaces exist for **override, inspection, and manual adjustment**—they are **not** assumed to be the first interaction.

The **product feel** may move toward conversational and activity-centric surfaces (e.g. chat-weighted flows, droids and teams, activity history, avatar or presence)—**illustrative north-star only**, not a committed screen list, build order, or shipped UI.

## Reference ecosystems (approximate only)

Rough **concept mapping** for alignment conversations—**not** schema parity, **not** one-to-one fields, **not** a commitment to mirror foreign configs.

| Area (approx.) | External inspiration (secondary) | HAM stance |
|----------------|----------------------------------|------------|
| Supervisory coordination | Hermes-style control | Hermes is the in-repo supervisory pillar; HAM UI orchestrates around that story. |
| Workforce / missions | Factory / Droid-style patterns | Specialist and mission patterns inform direction; HAM naming stays HAM-native. |
| Persona / character | ElizaOS-style patterns | Avatar/persona flavor informs UX direction; not Eliza config parity. |
| Tools / channels / memory flavor | OpenClaw-style patterns | Gateway and “soul” ideas inform leverage; HAM does not adopt SOUL.md as its native spec. |
| Repo truth | — | **`memory_heist`** remains the workspace/repo truth layer. |

## Shared workspace shape (near-term)

**Everyone sees everything by default**—no tenant isolation is required for the first shared-workspace iteration.

Access is **via a shared API key**; an **author** (or similar) field on records supports **attribution**, not access control. The **frontend reads** run history and registry-oriented data; **execution stays on the CLI** locally. A hosted execution path on Cloud Run or equivalent may follow; it is not committed.

## Principles that should survive any slice

- **HAM-native model first:** product and UX concepts are stated in **HAM’s own terms**; external frameworks are **secondary** references, not HAM’s primary language.
- **Not a thin wrapper:** HAM is not defined as a mandatory pass-through to Hermes, ElizaOS, OpenClaw, or Factory-native semantics.
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
- **Not a schema spec** for the six-concern model, run records, or future agent configuration storage.
