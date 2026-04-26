# HAM Capability Bundle Directory — v1 Specification

**Status:** Design / spec only (Phase 0). No implementation commitment.  
**Version:** 1.0-spec  
**Last updated:** 2026-04-24  

## 1. Purpose

Define a **HAM-native, versioned registry** of **atomic capabilities** and **composable bundles/templates** that operators use to assemble **agent profiles** and **workflow templates**—without treating HAM as “one LLM with plugins,” without executable registry records, and without smuggling execution into the HAM API server.

This document is the **contract sketch** for a future **Capability Bundle Directory**. It does **not** prescribe mutations to `.ham/settings.json`, Hermes config, MCP config, or profile files in v1.

**Related:** local computer-control roadmap and Phase 1 directory bundle — [`computer_control_pack_v1.md`](computer_control_pack_v1.md).

---

## 2. Architecture alignment (non-negotiables)

| Rule | Implication for Directory |
|------|---------------------------|
| Hermes = supervision, routing, critique, policy, learning **signals** | Directory entries **describe** what Hermes-facing skills/charters **mean**; Hermes is **not** the universal harness anchor for all capability types. |
| Cursor Cloud Agents / Droid / CLI = **execution** | Directory lists **required backends** and **tool/MCP allowlists** as **declared policy**, not runtime enforcement inside FastAPI. |
| `memory_heist` = workspace **truth injection** | Bundles may declare **context budgets** / instruction paths as **hints** for assembly; actual injection stays in Context Engine / chat assembly code paths. |
| Registry records = **data**, not behavior | No arbitrary code execution from directory rows; no `eval`, no embedded scripts as the source of truth. |
| Runs = **evidence** | No “levels,” fake progression, or marketplace gamification on directory rows; provenance pins are **metadata**. |
| ControlPlaneRun | Directory **may reference** read-only control-plane facts for **documentation** (“this bundle expects Droid workflows”); **must not** change `ControlPlaneRun` semantics or storage. |
| Payments | **Out of scope** for all phases in this spec’s non-goals. |

---

## 3. Current repo capability map (ground truth)

*Inspection basis: files listed in §15.*

### 3.1 Hermes runtime skills (catalog)

- **Vendored catalog:** `src/ham/data/hermes_skills_catalog.json` (+ `src/ham/hermes_skills_catalog.py`).
- **Read API:** `GET /api/hermes-skills/catalog`, `GET /api/hermes-skills/catalog/{catalog_id}` (`src/api/hermes_skills.py`).
- **Agent Builder coupling:** `HamAgentProfile.skills` in `src/ham/agent_profiles.py` validates against **Hermes catalog ids** (`hermes_runtime_skill_catalog_ids()`).

### 3.2 Hermes skills — live overlay

- **Module:** `src/ham/hermes_skills_live.py` — read-only join of **`hermes skills list`** (allowlisted CLI) + catalog.
- **Read API:** `GET /api/hermes-skills/installed`.

### 3.3 Hermes runtime inventory

- **Module:** `src/ham/hermes_runtime_inventory.py`.
- **Read API:** `GET /api/hermes-runtime/inventory` (`src/api/hermes_runtime_inventory.py`).
- **Remote deployments:** `HAM_HERMES_SKILLS_MODE=remote_only` disables local CLI inventory (honest degradation).

### 3.4 Hermes skills — install preview / apply (existing pattern)

- **Capabilities:** `GET /api/hermes-skills/capabilities`, `GET /api/hermes-skills/targets`.
- **Preview (no write):** `POST /api/hermes-skills/install/preview` — returns `proposal_digest`, `base_revision`, `config_diff`, `paths_touched`, etc.
- **Apply (guarded):** `POST /api/hermes-skills/install/apply` — requires `HAM_SKILLS_WRITE_TOKEN`, conflict checks, audit.
- **Reuse for Directory v1:** same **preview-first, digest + base_revision, token-gated apply** mental model; Directory v1 **only documents** preview; Phase 4 aligns with this pattern.

### 3.5 Cursor operator skills

- **Source:** `.cursor/skills/*/SKILL.md` on repo (or `HAM_REPO_ROOT`).
- **Loader:** `src/ham/cursor_skills_catalog.py`.
- **Read API:** `GET /api/cursor-skills` (see `src/api/server.py` index).
- **Semantics:** Operator **documentation / intent mapping** for chat control plane—not Hermes runtime install targets.

### 3.6 Cursor subagent charters

- **Source:** `.cursor/rules/subagent-*.mdc`.
- **Read API:** `GET /api/cursor-subagents` (`src/ham/cursor_subagents_catalog.py`).
- **Semantics:** Review/audit **charters**, not executable skills.

### 3.7 Droid registry & Factory workflows

- **Registry:** `src/registry/droids.py` — `DroidRecord` / `DEFAULT_DROID_REGISTRY` (data-only records; `metadata` bag).
- **Workflow policy:** allowlisted workflows in code (e.g. `src/ham/droid_workflows/registry.py`); skill narrative in `.cursor/skills/factory-droid-workflows/SKILL.md`.
- **Chat operator:** preview → confirm → launch with tokens (`HAM_DROID_EXEC_TOKEN` for mutating tiers).

### 3.8 Agent profiles (HAM Agent Builder)

- **Models:** `HamAgentProfile`, `HamAgentsConfig` in `src/ham/agent_profiles.py`; persisted via `src/ham/settings_write.py` under project settings (agents subtree).
- **Read/write:** `src/api/project_settings.py` — preview/apply/rollback with `HAM_SETTINGS_WRITE_TOKEN` for mutations.
- **Frontend:** `/agents` → `frontend/src/pages/AgentBuilder.tsx`.

### 3.9 Models / tiers

- **Catalog:** `src/api/models_catalog.py` — OpenRouter tiers, Cursor rows (chat disabled for Cursor slugs in gateway), `resolve_model_id_for_chat`.
- **Defaults:** `src/llm_client.py` — `get_default_model()`, `resolve_openrouter_model_name_for_chat()`.

### 3.10 Control plane runs (read-only reference)

- **API:** `GET /api/control-plane-runs`, `GET /api/control-plane-runs/{ham_run_id}` (`src/api/control_plane_runs.py`).
- **Use in Directory:** Optional **cross-links** in bundle metadata (“typical evidence: control_plane_run with `action_kind` X”). **Do not** extend schema or behavior.

### 3.11 `.ham` / settings conventions

- **Project settings:** `.ham/settings.json` — allowlisted writes via `settings_write` (includes **agents** subtree).
- **Runs:** `.ham/runs/*.json` — evidence blobs (not registry).
- **Config discovery:** `.ham.json` merge chain (see `VISION.md` / Context Engine).

### 3.12 Frontend surfaces today

| Route | Page | Role |
|-------|------|------|
| `/skills` | `HermesSkills.tsx` | Hermes runtime catalog, live overlay, install preview/apply |
| `/agents` | `AgentBuilder.tsx` | HAM agent profiles, Hermes skill ids |
| Diagnostics / settings | `UnifiedSettings.tsx`, overlays | Cursor API, env help, operator launcher context |

---

## 4. Core directory model (three layers)

### 4.1 Layer A — Capability Directory (atomic)

**Atomic entry kinds** (v1 enum; extensible with schema version):

| `kind` | Description | Repo anchor today (examples) |
|--------|-------------|------------------------------|
| `hermes_runtime_skill` | Hermes catalog skill id | `catalog_id` in vendored catalog |
| `cursor_operator_skill` | Repo skill slug | `.cursor/skills/.../SKILL.md` |
| `mcp_server_manifest` | Declared MCP server (future) | **No first-class store yet** — placeholder in v1 |
| `tool_policy_ref` | Named policy / allowlist reference | e.g. Droid workflow tier, env token name **as documentation** |
| `subagent_charter` | Cursor subagent rule | `subagent-*.mdc` id / path |
| `droid_workflow_stub` | Allowlisted `workflow_id` + narrative | `readonly_repo_audit`, `safe_edit_low`, etc. |

Atomic entries **do not** embed execution logic; they **point** to stable ids, paths, or manifests.

### 4.2 Layer B — Bundle / template

A **bundle** composes atomic ids + **policy metadata**:

- Hermes / Cursor skill ids
- Required **backend/runtime** (e.g. `hermes_cli_local`, `cursor_api`, `droid_local`, `openrouter_chat`)
- Tool/MCP **allowlist** (declarative strings; enforcement remains on execution plane)
- **Recommended model tier** (`auto` | `premium` | `explicit_openrouter_slug`) — **not** mandatory vendor lock-in
- **Memory/context budget** hints (e.g. “high_level”, or numeric budgets **TBD** with Context Engine)
- **Policy notes** (human-readable)
- **Evidence / run expectations** (what a successful run should produce; links to run kinds)

### 4.3 Layer C — Agent / team profile template

Maps bundle(s) onto **HAM-native** shapes:

- `HamAgentProfile`-compatible fields **template** (name pattern, description, `skills: []` from Hermes ids)
- **Team template** (ordered profiles, primary id) — **future**; v1 may be single-profile only
- **Provenance:** bundle id + version pin + checksum placeholder
- **No derived progression** on the template row

---

## 5. Proposed manifest schema (JSON examples)

### 5.1 Atomic capability entry

```json
{
  "schema_version": "capability.directory.v1",
  "kind": "atomic",
  "id": "atomic.cursor_skill.factory_droid_workflows",
  "atomic_kind": "cursor_operator_skill",
  "display": {
    "title": "Factory Droid workflows",
    "summary": "Preview and launch allowlisted droid exec workflows from chat."
  },
  "trust": {
    "lane": "first_party",
    "review_status": "approved",
    "source": {
      "type": "repo_path",
      "path": ".cursor/skills/factory-droid-workflows/SKILL.md"
    },
    "version_pin": "2026-04-24",
    "integrity": {
      "sha256": null,
      "signature": null
    }
  },
  "requirements": {
    "backends": ["droid_local", "ham_api_chat_operator"],
    "read_only": false,
    "mutates_workspace": true,
    "notes": "Mutating workflows require HAM_DROID_EXEC_TOKEN; see FACTORY_DROID_CONTRACT."
  },
  "refs": {
    "cursor_skill_slug": "factory-droid-workflows",
    "docs": ["docs/FACTORY_DROID_CONTRACT.md"]
  }
}
```

### 5.2 Bundle / template

```json
{
  "schema_version": "capability.directory.v1",
  "kind": "bundle",
  "id": "bundle.ham.audit_and_ship_v1",
  "version": "1.0.0",
  "display": {
    "title": "Audit → review → low-risk edit",
    "summary": "Read-only audit workflow plus optional low-risk edit path with tokens."
  },
  "trust": {
    "lane": "first_party",
    "review_status": "approved",
    "source": { "type": "bundled_registry", "registry_id": "ham.official.v1" },
    "integrity": { "sha256": null, "signature": null }
  },
  "composition": {
    "hermes_runtime_skill_ids": ["hermes.example.skill_one"],
    "cursor_operator_skill_slugs": ["factory-droid-workflows", "repo-context-regression-testing"],
    "subagent_charter_ids": ["subagent-security-review"],
    "droid_workflow_ids": ["readonly_repo_audit", "safe_edit_low"],
    "mcp_server_ids": [],
    "tool_policy_refs": ["policy.droid_exec_allowlist_v1"]
  },
  "runtime": {
    "required_backends": ["ham_api", "droid_cli", "openrouter_or_hermes_http"],
    "recommended_model_tier": "auto",
    "context_budget_hint": "standard",
    "policy_notes": [
      "Hermes supervises; Droid executes mutating steps.",
      "Do not attach community MCP without org review."
    ]
  },
  "evidence": {
    "expected_run_kinds": ["bridge", "control_plane_run", "droid_workflow"],
    "notes": "Progression and quality are inferred from run history, not from this bundle row."
  }
}
```

### 5.3 Agent / team profile template

```json
{
  "schema_version": "capability.directory.v1",
  "kind": "profile_template",
  "id": "profile_template.ham.builder_with_audit_skills",
  "version": "1.0.0",
  "display": {
    "title": "Builder + audit skills",
    "summary": "Primary agent with Hermes runtime skills and optional Cursor operator alignment."
  },
  "trust": {
    "lane": "first_party",
    "review_status": "draft",
    "source": { "type": "bundled_registry", "registry_id": "ham.official.v1" },
    "provenance": {
      "bundle_id": "bundle.ham.audit_and_ship_v1",
      "bundle_version": "1.0.0"
    }
  },
  "ham_agent_profile": {
    "id_pattern": "project.{slug}.builder_audit",
    "name_template": "{project_name} Builder (audit pack)",
    "description_template": "Uses bundle bundle.ham.audit_and_ship_v1 v1.0.0",
    "skills": ["hermes.example.skill_one"],
    "enabled": true
  },
  "team": {
    "primary_agent_id_pattern": "project.{slug}.builder_audit",
    "secondary_profiles": []
  }
}
```

---

## 6. Proposed type shapes (implementation-ready sketches)

### 6.1 Python (Pydantic-style, not shipped)

```python
# Sketch only — do not paste into production until Phase 1.

from typing import Any, Literal
from pydantic import BaseModel, Field

TrustLane = Literal["first_party", "verified_org", "community", "local_only", "unsigned"]
AtomicKind = Literal[
    "hermes_runtime_skill",
    "cursor_operator_skill",
    "mcp_server_manifest",
    "tool_policy_ref",
    "subagent_charter",
    "droid_workflow_stub",
]

class TrustBlock(BaseModel):
    lane: TrustLane
    review_status: Literal["draft", "approved", "rejected", "deprecated"]
    source: dict[str, Any]  # discriminated by type in v1.1
    version_pin: str = ""
    integrity: dict[str, str | None] = Field(default_factory=dict)

class AtomicCapability(BaseModel):
    schema_version: Literal["capability.directory.v1"] = "capability.directory.v1"
    kind: Literal["atomic"] = "atomic"
    id: str
    atomic_kind: AtomicKind
    display: dict[str, str]
    trust: TrustBlock
    requirements: dict[str, Any]
    refs: dict[str, Any] = Field(default_factory=dict)

class CapabilityBundle(BaseModel):
    schema_version: Literal["capability.directory.v1"] = "capability.directory.v1"
    kind: Literal["bundle"] = "bundle"
    id: str
    version: str
    display: dict[str, str]
    trust: TrustBlock
    composition: dict[str, list[str]]
    runtime: dict[str, Any]
    evidence: dict[str, Any] = Field(default_factory=dict)

class ProfileTemplate(BaseModel):
    schema_version: Literal["capability.directory.v1"] = "capability.directory.v1"
    kind: Literal["profile_template"] = "profile_template"
    id: str
    version: str
    display: dict[str, str]
    trust: TrustBlock
    ham_agent_profile: dict[str, Any]
    team: dict[str, Any] = Field(default_factory=dict)
```

### 6.2 TypeScript (interface sketch)

```ts
// Sketch only — for frontend consumption in later phases.

export type TrustLane =
  | "first_party"
  | "verified_org"
  | "community"
  | "local_only"
  | "unsigned";

export type AtomicKind =
  | "hermes_runtime_skill"
  | "cursor_operator_skill"
  | "mcp_server_manifest"
  | "tool_policy_ref"
  | "subagent_charter"
  | "droid_workflow_stub";

export interface TrustBlock {
  lane: TrustLane;
  review_status: "draft" | "approved" | "rejected" | "deprecated";
  source: Record<string, unknown>;
  version_pin: string;
  integrity: { sha256?: string | null; signature?: string | null };
}

export interface AtomicCapability {
  schema_version: "capability.directory.v1";
  kind: "atomic";
  id: string;
  atomic_kind: AtomicKind;
  display: { title: string; summary: string };
  trust: TrustBlock;
  requirements: Record<string, unknown>;
  refs?: Record<string, unknown>;
}

export interface CapabilityBundle {
  schema_version: "capability.directory.v1";
  kind: "bundle";
  id: string;
  version: string;
  display: { title: string; summary: string };
  trust: TrustBlock;
  composition: Record<string, string[]>;
  runtime: Record<string, unknown>;
  evidence?: Record<string, unknown>;
}

export interface ProfileTemplate {
  schema_version: "capability.directory.v1";
  kind: "profile_template";
  id: string;
  version: string;
  display: { title: string; summary: string };
  trust: TrustBlock;
  ham_agent_profile: Record<string, unknown>;
  team?: Record<string, unknown>;
}
```

---

## 7. Proposed read-only API (v1)

All responses include `schema_version` and `kind` at top level. **No mutations** in Phase 1–2.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/capability-directory` | Index: counts, schema version, trust lanes present, links to sub-resources. |
| GET | `/api/capability-directory/capabilities` | List atomic capabilities (filters: `atomic_kind`, `trust_lane`). |
| GET | `/api/capability-directory/capabilities/{id}` | Single atomic. |
| GET | `/api/capability-directory/bundles` | List bundles. |
| GET | `/api/capability-directory/bundles/{id}` | Single bundle (optional `?version=`). |
| POST | `/api/capability-directory/bundles/{id}/preview-apply` | **Dry-run only in v1:** returns a **proposal** describing how a bundle would map to current project/agent state—**no writes**. Response shape aligned with existing preview patterns (`proposal_digest`, `base_revision`, human-readable `plan`, `warnings`). |

**Auth:** Align with existing operator gates (`get_ham_clerk_actor` / deployment policy) same as Hermes skills routes.

**Note on `preview-apply`:** Name reflects **future** Phase 3–4 alignment with settings/Hermes install apply; **v1 response must not** mutate `.ham/settings.json`, Hermes config, or MCP config.

---

## 8. UI placement (product recommendation)

**Recommendation: primary entry under `/skills` (Hermes Skills) as a third tab or sub-nav: “Directory”.**

Rationale:

- **Skills** is already where operators reconcile **catalog vs live overlay vs install**; the Directory is **another catalog**, but **cross-cutting** (Hermes + Cursor + Droid).
- **Agent Builder** should **consume** bundle output (e.g. “Apply template” later) but should not own the **trust/provenance** story—avoid turning `/agents` into a marketplace.
- **Diagnostics → Hermes runtime** should keep **observability** (inventory, live CLI); linking *from* Directory rows *to* runtime inventory is good; making Diagnostics the home would bury **Cursor/Droid** capabilities and confuse “what is wrong” vs “what can I add.”

**Secondary:** Deep-link from **Agent Builder** (“Browse capability bundles”) opening Directory with pre-filter.

**Avoid:** A standalone top-level nav **until** Phase 2 proves usage; then a `/directory` route can alias the same page.

---

## 9. Trust and provenance model

| Lane | Meaning | Default install visibility |
|------|---------|----------------------------|
| `first_party` | Shipped with HAM repo or official registry | Shown first; highest trust |
| `verified_org` | Signed by org key (future) | Shown with badge |
| `community` | Third-party manifest | Strong warnings; may be hidden on strict hosts |
| `local_only` | Operator dropped JSON into local dir | Never leaves machine |
| `unsigned` | Explicit unverified | Same as community; **never** imply security |

**Fields (required on every row):**

- `trust.lane`
- `trust.review_status`
- `trust.source` (URL, repo path, or bundled registry id)
- `trust.version_pin` (semver or date **or** git sha **string**)
- `trust.integrity.sha256` / `signature` (nullable placeholders in v1)

**`requirements.read_only` vs `mutates_workspace`:** Must be explicit so UI can badge **read-only vs mutating**.

---

## 10. Preview / apply model (reuse without v1 mutation)

**Existing patterns to mirror:**

| Pattern | Location | Reuse |
|---------|----------|--------|
| Hermes skill install preview | `POST /api/hermes-skills/install/preview` | Digest + diff + warnings |
| Hermes skill install apply | `POST /api/hermes-skills/install/apply` | Token + `proposal_digest` + `base_revision` |
| Project settings preview | `src/ham/settings_write.preview_project_settings` | Diff for `.ham/settings.json` subtree |

**Directory v1:**

- Implement **only** documentation + **GET** list/detail.
- Optional **POST preview-apply** returns a **synthetic plan** (e.g. “would add Hermes skill ids X to profile Y”) **without** calling `apply_project_settings` or `apply_shared_install`.

**Phase 3:** Wire preview to real diff generators (still no apply).  
**Phase 4:** Single guarded apply endpoint with **`HAM_CAPABILITY_APPLY_TOKEN`** (name TBD) and conflict semantics like settings/skills apply.

---

## 11. Risks

| Risk | Mitigation |
|------|------------|
| Arbitrary code execution via manifests | Schema forbid code fields; validate ids against allowlists; static first-party registry only in Phase 1. |
| Path / secret leakage | No raw home paths in public directory JSON; redact like `hermes_runtime_inventory` / overlay code. |
| Fake “marketplace” confusion | Brand as **Directory**; no payments; clear **trust lanes**. |
| Fake progression | Never store XP/level on rows; link to **runs** only. |
| Brittle model/vendor coupling | Use **tiers** + optional explicit slug; document gateway modes (`http` vs `openrouter`). |
| Breaking Agent Builder validation | Profile templates must produce **`HamAgentProfile`-compatible** skill ids only; CI check catalog membership. |
| Confusing skills / tools / MCP | Glossary in UI; atomic `atomic_kind` discriminator; color badges. |

---

## 12. Phased implementation plan

| Phase | Scope |
|-------|--------|
| **0** | This spec + review (no code). |
| **1** | Static first-party JSON (or Python module) registry in repo; **read-only** FastAPI routes; tests for schema validation only. |
| **2** | UI: Directory panel under **Skills**; list/detail; trust badges; links to existing Hermes/Cursor APIs. |
| **3** | `preview-apply` **dry-run** returning structured plan + digest (no mutation). |
| **4** | Guarded apply (token + audit) for **one** narrow path (e.g. agent profile only **or** Hermes install only)—expand deliberately. |

---

## 13. Explicit non-goals (v1 / Phase 0–2)

- No payment, billing, or “store” checkout.
- No arbitrary code execution or downloadable binaries from Directory rows.
- No MCP server hosting inside HAM API.
- No mutation of `.ham/settings.json`, Hermes `config.yaml`, MCP configs, or agent files **until Phase 4** and a separate security review.
- No changes to **ControlPlaneRun** persistence or public field semantics.
- No Hermes-as-sole-harness requirement for all capability kinds.
- No replacement of Cursor/Droid execution with in-API tool runs.
- No gamification or progression metrics on directory rows.

---

## 14. Suggested commit message (after review)

```text
docs(capabilities): define bundle directory v1
```

---

## 15. Files inspected for this spec

- `VISION.md`
- `PRODUCT_DIRECTION.md`
- `AGENTS.md` (pillar index, `ham_cli`, ControlPlaneRun doc pointers)
- `src/ham/agent_profiles.py`
- `src/api/hermes_skills.py`
- `src/ham/hermes_skills_live.py`
- `src/ham/hermes_skills_catalog.py` (referenced via API)
- `src/ham/hermes_runtime_inventory.py`
- `src/api/hermes_runtime_inventory.py`
- `src/ham/cursor_skills_catalog.py`
- `src/api/project_settings.py` (preview/apply pattern)
- `src/registry/droids.py`
- `src/api/control_plane_runs.py`
- `src/api/server.py` (route index)
- `frontend/src/App.tsx` (routes)
- `.cursor/skills/factory-droid-workflows/SKILL.md`
- `.cursor/rules/registry-record-conventions.mdc`

---

## 16. Files created / changed (this deliverable)

| Action | Path |
|--------|------|
| **Created** | `docs/capabilities/capability_bundle_directory_v1.md` |

No other files modified.
