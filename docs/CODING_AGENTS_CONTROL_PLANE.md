# Coding Agents Control Plane

**Status:** vocabulary + product-narrative spec. **No runtime claims.**

This document defines the **operator-facing cockpit vocabulary** for HAM's
multi-provider coding-agents surface. It sits **above** two existing,
already-shipped substrates and **does not redefine them**:

- [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) — durable, factual
  per-launch record (`ControlPlaneRun`).
- [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) — what a
  harness must do to participate honestly (capability registry, digest
  policy, mapped lifecycle).

This file is the **product-narrative layer**: how operators reason about a
**coding work order**, which **coding agent provider** runs it, and how
provider runs roll back up into one cockpit. It is **not** an
orchestration framework, a mission graph, a queue, a runtime, or an
adapter ABC.

---

## 1. Purpose and non-purpose

**Purpose**

- Give operators and agents one vocabulary for "ask a coding agent to do
  work, observe its run, gate the commit boundary, audit the outcome"
  across providers.
- Name the four providers HAM actually cares about today, even when only
  two are implemented.
- Define what an adapter must, may, and must not do — anchored to the
  rules already in [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md).
- Sequence subsequent implementation PRs behind a stable cockpit
  definition.

**Non-purpose**

- **Not** a re-spec of `ControlPlaneRun` schema, lifecycle, caps, or
  audit pointers — those live in [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md).
- **Not** a cross-provider scheduler, mission graph, queue, retry
  policy, or autonomy substrate.
- **Not** a runtime adapter framework. The
  [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) §10
  rule still holds: do not build `HarnessAdapter` / plugin loaders
  before a third real harness lands.
- **Not** marketing copy for "HAM Agent Mode". High-autonomy framing
  remains **GoHAM** as defined in [`VISION.md`](../VISION.md) and
  [`HAM_THREE_LANE_FINISH_LINE.md`](HAM_THREE_LANE_FINISH_LINE.md).

---

## 2. Where this sits

```
+-------------------------------------------------------------------+
|  Operator cockpit (this doc — vocabulary only)                    |
|                                                                   |
|   CodingWorkOrder  --(commit boundary)-->  CodingAgentRun         |
|   (preview-stage)                          (alias for             |
|                                             ControlPlaneRun)      |
+-------------------------------------------------------------------+
                                |
                                v
+-------------------------------------------------------------------+
|  Factual run substrate                                            |
|    docs/CONTROL_PLANE_RUN.md                                      |
|    src/persistence/control_plane_run.py                           |
|    ControlPlaneRun: provider, proposal_digest, base_revision,     |
|      mapped status, status_reason, external_id, audit_ref         |
+-------------------------------------------------------------------+
                                |
                                v
+-------------------------------------------------------------------+
|  Harness behavior + capability registry                           |
|    docs/HARNESS_PROVIDER_CONTRACT.md (authoritative human table)  |
|    src/ham/harness_capabilities.py    (read-only mirror)          |
+-------------------------------------------------------------------+
                                |
                                v
+-------------------------------------------------------------------+
|  Provider modules (native; not flattened)                         |
|    src/ham/cursor_agent_workflow.py         (cursor_cloud_agent)  |
|    src/ham/droid_workflows/preview_launch.py (factory_droid)      |
|    src/integrations/cursor_cloud_client.py                        |
|    src/integrations/droid_runner_client.py                        |
+-------------------------------------------------------------------+
```

The cockpit layer **renames** existing concepts so operators can talk
about them without leaking provider internals. It does **not** add a
new persistence layer, queue, or graph.

---

## 3. CodingWorkOrder

A **CodingWorkOrder** is the **preview-stage** description of work the
operator wants a coding agent to perform. It is **not** a durable row
on disk in v1; it lives in the operator/preview phase and **becomes
durable as one or more `ControlPlaneRun` rows after the commit
boundary** (see §6 below and
[`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) §4).

**Conceptual fields (vocabulary, not a Pydantic model)**

| Field | Meaning | Notes |
|------|---------|-------|
| `project_id` | HAM project registry id | Must resolve in `ProjectStore`. |
| `intent` | Short operator-readable description | Free text; capped by the existing operator/chat path. |
| `repo` | Repository identity | For `cursor_cloud_agent`: remote GitHub URL. For `factory_droid`: registered local project root. |
| `branch` / `ref` | Optional ref hint | Provider-native semantics. |
| `scope` | `read_only` / `safe_edit` / `mutating` | Maps to existing droid workflow tiers + Cursor PR/branch options. |
| `approval_policy` | Operator-side policy for commit + deploy gates | Sourced from `mission_deploy_approval_mode` and operator tokens; **not** invented here. |
| `target_pr` | Optional follow-up target (Cursor only today) | Cursor proxy follow-up path; **not** digest-gated. |
| `provider_preference` | Optional hint | Honored only if the chosen provider is implemented and capability-compatible (§5). |

**Rules**

- A CodingWorkOrder **must** carry a digest-able description before it
  can cross the commit boundary. Digest computation stays
  **per-provider**: `compute_cursor_proposal_digest` for Cursor,
  `compute_proposal_digest` + `REGISTRY_REVISION` for Droid. There is
  **no** universal digest.
- A CodingWorkOrder is **not** persisted as a draft `ControlPlaneRun`
  row in v1 (matches [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) §5).
- A CodingWorkOrder may produce **0 or 1** `ControlPlaneRun` per commit
  in v1 — no graph, no parent/child rows.

---

## 4. CodingAgentProvider registry

This table is the **product-narrative** view of providers HAM cares
about. It mirrors the **authoritative** rows in
[`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) §6 and
adds **planned-only** entries that are not yet in
`src/persistence/control_plane_run.py::ControlPlaneProvider`.

| provider key | display name | family | status today | persisted in `ControlPlaneProvider` enum? |
|--------------|--------------|--------|--------------|--------------------------------------------|
| `cursor_cloud_agent` | Cursor Cloud Agent | `remote_http_agent` | implemented | yes |
| `factory_droid` | Factory Droid | `local_subprocess` | implemented | yes |
| `claude_code` | Claude Code | `local_cli_planned` | **planned_candidate** | **no** (do not add until adapter PR) |
| `opencode_cli` | OpenCode CLI | `local_cli_planned` | **planned_candidate** | **no** (matches existing doc-only stance — see [`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md)) |

**Rules**

- A planned provider **must not** be referenced as if `ControlPlaneRun`
  or operator flows already support it. Planned rows are **vocabulary
  only** until a separate PR lands the enum value, capability mirror
  row, and adapter module.
- The authoritative bool flags and digest/status/audit pointers live in
  [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) §6.
  This file does **not** duplicate them.

---

## 5. CodingAgentRun lifecycle

**`CodingAgentRun` is a product-narrative alias for `ControlPlaneRun`.**
It does not introduce a new model, new states, new caps, or new audit
pointers. The fields and lifecycle are exactly those defined in
[`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) §5–§6:

- `running` — HAM has submitted work (launch accepted / runner going).
- `succeeded` — terminal success (provider-specific mapping).
- `failed` — terminal failure (mapped or runner error).
- `unknown` — cannot classify (unmapped/ambiguous status, missing
  observation). **Required honesty** for Cursor strings outside the
  conservative map.

The cockpit **must** preserve the same `status_reason` discipline and
the bounded `last_provider_status` cap. There is **no** new state, no
`pending` / `dispatched` / `stale` introduced here.

---

## 6. Approval gates

The cockpit names existing gates; it does not invent new ones.

| Gate | Where it lives today | What the cockpit calls it |
|------|----------------------|---------------------------|
| Operator commit boundary | `verify_cursor_launch_against_preview` (Cursor); `verify_launch_against_preview` (Droid) | "Confirm work order" |
| HAM launch bearer | `HAM_CURSOR_AGENT_LAUNCH_TOKEN` (Cursor operator path) | "Launch token" |
| Mutating workflow bearer | `HAM_DROID_EXEC_TOKEN` (Droid `safe_edit_low`) | "Mutating-scope token" |
| Deploy approval mode | `mission_deploy_approval_mode` snapshot on `ManagedMission` create | "Deploy approval policy" |
| Optional PR-merge gating | Operator-only today; `gh pr merge --auto` is **not** allowed for social/autonomy/secrets/deploy/branch-protection per [`AGENTS.md`](../AGENTS.md) | "PR-merge gate" |

**Rules**

- The cockpit **must not** weaken any of these. It surfaces them; it
  does not bypass them.
- Hermes does **not** drive lifecycle. Hermes review remains
  advisory-only on the Cursor managed-mission path
  ([`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md)
  Phase C) and does not become a `status` source of truth.

---

## 7. Audit events

The cockpit reads from sinks that already exist; it does **not**
introduce a new audit store.

| Sink | Source today | Used by cockpit for |
|------|--------------|---------------------|
| `cursor_jsonl` | `src/ham/cursor_agent_workflow.py` | Cursor launch/status audit lines. |
| `droid_jsonl` | `<project_root>/.ham/_audit/droid_exec.jsonl` | Droid exec audit. |
| `project_mirror` | Optional CP run mirror under `<project_root>/.ham/control_plane/runs/` | Local human inspection. |
| Operator audit | `src/ham/operator_audit.py` | Operator action lines (separate from CP). |
| Runner audit (remote droid) | `HAM_DROID_RUNNER_AUDIT_FILE` on the runner host | Append-only runner-side outcome lines. |

**Rules**

- Full provider payloads stay **native**. The cockpit displays
  **bounded** excerpts (capped per `CONTROL_PLANE_RUN.md` §6) and
  **pointers** (`audit_ref`).
- Redaction stays at the existing layers: `redact()` in
  `src/ham/social_delivery_log.py`-style sinks, gitleaks `--redact` in
  CI, runner-side "no secrets / no argv / no prompt" rule.
- `audit_id` correlation between operator audit and `ControlPlaneRun`
  remains optional and best-effort, as today.

---

## 8. Provider adapter contract

This section restates the cockpit's view of what a provider adapter
must do. The **authoritative rules** are in
[`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) §5 and §10.

**Required**

1. Bind work to a HAM `project_id` and a stable provider key.
2. Use a **per-provider** `proposal_digest` and `base_revision`. No
   universal digest. Reject stale or mismatched input on launch when
   the operator path applies.
3. After commit, write a `ControlPlaneRun` per
   [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md). One row per
   committed launch in v1.
4. Map outcomes into HAM's mapped lifecycle with `status_reason`.
   `unknown` is the honest answer for ambiguous provider status.
5. Append-only audit + `audit_ref` pointer. Never inline full provider
   blobs into the run row.

**Optional**

- Operator preview (digest-only is acceptable in theory; Cursor and
  Droid both have interactive preview today).
- Long-running status poll (Cursor); not all providers will have one.
- Stable `external_id` (Cursor agent id, Droid `session_id`).
- Follow-up / conversation surfaces (Cursor today; **not**
  digest-gated).

**Forbidden**

- Smuggling unbounded provider data into `ControlPlaneRun`.
- Pretending a planned provider is implemented.
- Letting Hermes drive `status` truth.
- Building a generic `HarnessAdapter` ABC before a third real harness
  exists.
- Introducing a new lifecycle state outside `running` / `succeeded` /
  `failed` / `unknown`.

---

## 9. Provider mapping examples

The four providers, mapped through the CodingWorkOrder vocabulary.
Italics mark **planned** rows that have **no implementation today**.

| Field / aspect | `cursor_cloud_agent` ✅ | `factory_droid` ✅ | _`claude_code` 🟡 planned_ | _`opencode_cli` 🟡 planned_ |
|---|---|---|---|---|
| Family | `remote_http_agent` | `local_subprocess` | _`local_cli_planned`_ | _`local_cli_planned`_ |
| `repo` shape | Remote GitHub URL (resolved) | Registered local project root | _Local project root (intent)_ | _Local project root (intent)_ |
| Preview path | `cursor_agent_preview` (digest + pending summary) | `droid_preview` (allowlisted workflow + digest) | _TBD; doc-only_ | _TBD; doc-only_ |
| Launch path | `cursor_agent_launch` + `HAM_CURSOR_AGENT_LAUNCH_TOKEN` | `droid_launch` + (optional) `HAM_DROID_EXEC_TOKEN` | _TBD_ | _TBD_ |
| Digest source | `compute_cursor_proposal_digest` + `CURSOR_AGENT_BASE_REVISION` | `compute_proposal_digest` + `REGISTRY_REVISION` | _TBD_ | _TBD_ |
| Status / readback | `GET /v0/agents/{id}` + `map_cursor_raw_status` | Mostly terminal at launch via `droid_outcome_to_ham_status` | _TBD_ | _TBD_ |
| `external_id` | Cursor agent id | `session_id` from runner JSON when present | _TBD_ | _TBD_ |
| Audit sink | `cursor_jsonl` (+ optional project mirror) | `droid_jsonl` under `.ham/_audit/` | _none in CP yet_ | _none in CP yet_ |
| Follow-up | REST proxies (`/api/cursor/.../followup`); **not** digest-gated | Not exposed as Cursor-style follow-up in v1 | _TBD_ | _TBD_ |
| `ControlPlaneProvider` enum value present? | **yes** | **yes** | **no** (must not be added until adapter PR) | **no** (matches [`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md)) |
| Topology note | Remote agent against hosted repo | Local `droid exec` on registered project root | _Local CLI; verification work not started_ | _Local CLI; verification per [`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md)_ |

**Why Claude Code is listed as planned**

Claude Code is referenced via the **Claude Agent SDK** readiness path
in `src/api/workspace_tools.py` and
`src/ham/worker_adapters/claude_agent_adapter.py` (presence-only auth
hints + optional gated one-shot smoke). That is **workspace-tool
readiness**, **not** a coding-agent control-plane provider. A
`claude_code` row now exists in `src/ham/harness_capabilities.py` as a
`planned_candidate` (vocabulary only, `implemented=False`,
`supports_operator_launch=False`), but there is **no** `claude_code`
value in `ControlPlaneProvider` and **no** adapter module under
`src/ham/`. The cockpit names it as planned so a future PR can add the
enum value and adapter module honestly.

**Why OpenCode is listed as planned**

OpenCode appears in
[`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) §6 with
`registry_status=planned_candidate` and `implemented=False`, and in
[`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md) as a real-host
verification track. It has **no** enum value in `ControlPlaneProvider`
and **no** runtime today. Same rule: vocabulary only until an adapter
PR lands.

---

## 10. Out of scope (explicit)

This document does **not** define or imply any of the following, and
the implementation PRs that follow it will be **scoped per provider**:

- Runtime execution, mission graph, queue, retry policy, parent/child
  runs, or cross-provider scheduling.
- Hosted config changes, secret rotation, GCP / Vercel / Firestore
  edits.
- Branch protection edits, Dependabot rule edits, CI promotion from
  warning-only to blocking.
- PR auto-merge for any social / autonomy / secrets / deploy /
  branch-protection PR.
- New autonomy modes. High-autonomy framing remains **GoHAM** per
  [`VISION.md`](../VISION.md).
- Live social actions (HAMgomoon / Telegram / X publish paths).
- Frontend cockpit screen — implementation PR sequenced after this
  vocabulary lands.
- OpenAPI regeneration, ESLint adoption, strict-typing flag-flips,
  formatter sweeps, monorepo consolidation.
- A generic `HarnessAdapter` ABC, plugin loader, or capability
  framework. The
  [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) §10
  rule "Add a third harness before inventing a large framework" still
  applies.

---

## 11. Subsequent implementation PR sequence

After this vocabulary lands, future PRs (each scoped, each separate)
can proceed in this order:

1. `chore(agents): add claude_code + opencode_cli to ControlPlaneProvider enum (planned-flag only)`
   — registry value + capability mirror row only; no runtime wiring;
   tests pin enum surface.
2. `feat(agents): claude_code adapter MVP (preview + launch + audit)`
   — parallel to `cursor_agent_workflow.py`.
3. `feat(agents): opencode_cli adapter MVP` — parallel to
   `droid_workflows/preview_launch.py`, gated on
   [`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md) results.
4. `feat(frontend): coding-agents cockpit screen` — surfaces
   CodingWorkOrders + CodingAgentRuns across providers.

This file does **not** ship any of the above.

---

## 12. Cross-references

| Document | Role |
|----------|------|
| [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) | Durable run record schema, commit boundary, caps, audit pointers. |
| [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) | Authoritative harness behavior + capability registry. |
| [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) | Operator/chat phases, tokens, product behavior. |
| [`FACTORY_DROID_CONTRACT.md`](FACTORY_DROID_CONTRACT.md) | Phase 1 droid exec integration, runner seam. |
| [`HAM_DROID_RUNNER_SERVICE.md`](HAM_DROID_RUNNER_SERVICE.md) | Remote droid runner audit boundary. |
| [`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md) | OpenCode real-host verification before any implementation. |
| [`OPENCODE_VERIFICATION_RESULT.md`](OPENCODE_VERIFICATION_RESULT.md) | Latest OpenCode verification result. |
| [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Managed mission phase status (A truth, B correlation, C hermes-advisory, D narrow board lane). |
| [`MISSION_AWARE_FEED_CONTROLS.md`](MISSION_AWARE_FEED_CONTROLS.md) | Mission feed scoping by `mission_registry_id`. |
| [`HAM_THREE_LANE_FINISH_LINE.md`](HAM_THREE_LANE_FINISH_LINE.md) | Lane 3 (cloud / hosted agent) product-truth checklist. |
| [`AGENTS.md`](../AGENTS.md) | Cloud Agent / HAM VM Git policy and PR hygiene. |
| [`VISION.md`](../VISION.md) | Pillars, GoHAM framing, stable bets. |

---

*This document is vocabulary + product narrative for the
coding-agents cockpit. It does not change `ControlPlaneRun`, the
capability registry, the operator/chat path, or any provider module.*
