# HARNESS_PROVIDER_CONTRACT — HAM harness / provider contract

This document is the **authoritative** description of what it means for a **harness** (provider integration) to participate honestly in HAM. It is grounded in the **two harnesses that exist in the repo today**: **Cursor Cloud Agents** and **Factory Droid** (`droid exec` workflows). It is **not** a promise of full cross-provider orchestration, mission graphs, or scheduling.

| Concern | Document |
|--------|----------|
| **Durable run record** (fields, commit boundary, schema) | [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) |
| **Chat operator** phases, tokens, product UX | [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) |
| **OpenCode** real-host verification (before any implementation) | [`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md) |
| **This doc** | Provider *behavior*, *capabilities*, *preservation* rules |

---

## 1. Purpose / scope

**What this contract is for**

- Defining what HAM **expects** from a harness so that preview/launch/status/audit can stay **bounded**, **factual**, and **reviewable**.
- Stating which behaviors are **shared** vs **provider-specific** without flattening real differences.
- Preserving the **current Cursor** and **Droid** implementations as **first-class** inputs: the contract **describes** them; it does not rewrite them in theory.

**What it is not for**

- Cross-provider “mission” orchestration, queues, parent/child runs, or global scheduling.
- Replacing [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) (factual run substrate).
- Defining a generic **adapter framework** or abstract base class for all future harnesses.

**Explicit scope**

- **In scope:** Cursor Cloud Agents; Factory Droid / droid exec workflows, as implemented under `src/ham/cursor_agent_workflow.py`, `src/ham/droid_workflows/`, and operator routes in `src/ham/chat_operator.py`.

**Explicit non-scope (this step)**

- **Hermes** is **not** the harness contract anchor. Hermes may remain an **adjacent** advisory/runtime concern (e.g. review, chat gateway). **Provider lifecycle, digests, and `ControlPlaneRun` truth** are **not** defined by Hermes in this document.

---

## 2. Core thesis

- **Capability-based contract, not forced symmetry** — Each harness **advertises** what it can do (e.g. preview, long-running status poll, follow-up) instead of HAM assuming identical verbs for every provider.
- **Provider-native fidelity** — Repository URLs, PR flags, and `droid exec` argv belong in **Cursor** and **Droid** modules, not in a lowest-common-denominator DTO.
- **`ControlPlaneRun` is the factual substrate** for **committed** launches and HAM’s mapped lifecycle — see [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md). Native payloads stay **out** of the row except **capped** excerpts and **pointers** to audit.
- **Avoid LCD abstractions** — A single “universal `Launch`” or one digest schema for all providers would be **dishonest** given how Cursor and Droid actually work.

---

## 3. Current Cursor Cloud Agent model

**Plain English:** The user (via chat/operator) requests a **preview** of a proposed Cursor run: HAM computes a **cryptographic `proposal_digest`** and constant **`base_revision`** from a **canonical** description of the task (GitHub **repository**, ref, model, optional PR/branch options, task text, etc.). That preview is **not** a `ControlPlaneRun` row. When the user **confirms** and sends **`cursor_agent_launch`**, HAM **verifies** the digest matches the preview, requires a **HAM operator bearer** (`HAM_CURSOR_AGENT_LAUNCH_TOKEN`) separate from the **Cursor API key**, then calls Cursor’s `POST /v0/agents`. HAM writes a **`ControlPlaneRun`** and append-only **JSONL** audit. **Status** is observed via `GET /v0/agents/{id}`; HAM may **update** the same run when correlating on `(project_id, provider, external_id)` with the Cursor **agent id**.

A **second** path exists: dashboard/CI **HTTP proxies** under `/api/cursor/...` (e.g. launch, follow-up, conversation) that **do not** go through the same **digest + operator commit** path. Those surfaces must stay **documented** as **distinct**; they are not interchangeable with the operator contract without extra policy.

**Non-negotiables to preserve**

| Rule | Rationale |
|------|-----------|
| **Digest canonicalization** | `compute_cursor_proposal_digest` / fixed JSON shape; changing it breaks stored digests and audit meaning. |
| **Verify at launch** | `verify_cursor_launch_against_preview` — reject stale `base_revision` or digest mismatch before calling Cursor. |
| **Separate HAM launch token vs Cursor API key** | API key calls Cursor; **bearer** on `cursor_agent_launch` is the HAM **commit** gate. |
| **Conservative status mapping; `unknown` allowed** | `map_cursor_raw_status` — unmapped provider strings → HAM `unknown` + `status_reason` (not fake certainty). |
| **Distinct direct proxy surfaces** | Follow-up / conversation / ad-hoc launch via `src/api/cursor_settings.py` — **not** digest-gated like the operator path. |

**Already normalized (HAM truth)**

- `ControlPlaneRun` with `provider = cursor_cloud_agent`, `proposal_digest`, `base_revision`, mapped `status` / `status_reason`, bounded `last_provider_status`, `external_id` (agent id), `audit_ref`, optional `project_root` (e.g. mirror for JSON copy) — not Cursor’s execution root.

**Stays Cursor-specific**

- `resolve_cursor_repository_url`, `compose_prompt_for_cursor`, `summarize_cursor_agent_payload`, Cursor JSON field names, PR URL from `target`, `CursorCloudApiError` handling, HTTP client in `cursor_cloud_client` (Bearer) vs proxy style in `cursor_settings`.

---

## 4. Current Droid model

**Plain English:** A **local** project root must be **accessible** to the API host. The user picks an **allowlisted workflow** (registry in `droid_workflows`) and a user focus; HAM builds a **preview** with a **proposal digest** tied to **registry revision** and workflow, then **`droid_launch`** after **confirm** and digest match. Execution is **local** `droid exec` (or runner path); outcomes map to HAM status via `droid_outcome_to_ham_status`. A **`ControlPlaneRun`** is written for the committed launch; **`workflow_id`** is set; **`external_id`** may be a **session_id** from parsed stdout when present. Audit is project-local JSONL (`droid_jsonl` sink) plus control-plane file under `HAM_CONTROL_PLANE_RUNS_DIR`.

**Non-negotiables to preserve**

- **Local root** and registry-backed **workflows** — not interchangeable with a remote-only harness.
- **Per-workflow** digest and **`REGISTRY_REVISION` as `base_revision` family** — distinct from Cursor’s `CURSOR_AGENT_BASE_REVISION`.
- **Mutating workflows** and **`HAM_DROID_EXEC_TOKEN`** (and operator policy) as implemented — do not paper over policy in a generic “launch”.

**Already normalized**

- Same `ControlPlaneRun` shape: `provider = factory_droid`, `workflow_id` required, `proposal_digest`, `base_revision` from registry revision, `external_id` optional, `audit_ref`, `project_root` as the **actual** project directory.

**Stays Droid-specific**

- `get_workflow`, `build_exec_argv`, `execute_droid_workflow`, stdout JSON parse, droid JSONL path under `.ham/_audit/`.

---

## 5. Shared harness / provider contract

A harness is **“HAM-orchestratable”** in the sense of this document if it can meet the following **without** lying about topology or smuggling unbounded provider data into the run record.

**Minimum required**

| # | Requirement |
|---|-------------|
| 1 | **Bind** work to a HAM `project_id` and a stable `provider` identifier (see `ControlPlaneProvider` in `control_plane_run.py`). |
| 2 | **Commit boundary** — use per-provider `proposal_digest` and `base_revision` where HAM enforces; reject stale/mismatched input on launch when applicable. |
| 3 | **Launch record** — after a committed launch path, create/update a **`ControlPlaneRun`** per [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) (v1: no durable row for preview alone). |
| 4 | **Terminal honesty** — map outcomes into HAM’s lifecycle (`running` / `succeeded` / `failed` / `unknown`) with **`status_reason`**. **Unknown** is valid when the provider is ambiguous. |
| 5 | **Audit linkage** — append-only audit + `ControlPlaneAuditRef`-style pointer; large native payloads **not** on `ControlPlaneRun`. |

**Optional in the abstract contract (both current harnesses still implement operator preview; future harnesses might not)**

| Capability | Note |
|------------|------|
| Operator **preview** | May be “digest-only from config” in theory; HAM’s Cursor and Droid **today** have interactive preview. |
| **Status / readback** | Long-running **poll** (Cursor) vs **mostly terminal** at launch (Droid v1) — not identical. |
| **`external_id`** | Optional; enables correlation (Cursor agent id, droid `session_id`). |

**Common lifecycle / readback** — HAM’s mapped `status`, `status_reason`, bounded `last_provider_status`, timestamps: see `ControlPlaneRun` and mappers in `src/persistence/control_plane_run.py`.

**Common identity** — HAM `ham_run_id` is primary; **`external_id`** is provider’s handle when available.

**Common audit / CP linkage** — JSONL (or equivalent) + `audit_ref` on the run; operator audit lines remain separate as today.

**The contract does NOT require**

- Identical preview or launch **payloads** across harnesses.
- **Follow-up** or **conversation** as control-plane verbs.
- All harnesses to support **status poll**.
- **Hermes** to drive provider lifecycle.
- **Full provider JSON** in `ControlPlaneRun`.

---

## 6. Read-only capability registry (authoritative)

This table is the **human-readable** source of the harness **vocabulary**. A **read-only** Python mirror lives in `src/ham/harness_capabilities.py` for the same data (import-safe; **no** dispatch).

**Rules**

- **Implemented** rows match live HAM behavior for `Cursor` and `Droid` (`ControlPlaneProvider` in `src/persistence/control_plane_run.py`).
- **Planned** rows describe **candidates** only: `registry_status=planned_candidate` and `implemented=False` in `harness_capabilities.py`; they **must not** be used as if `ControlPlaneRun` or operator flows already support that provider.
- Bools are **coarse**; the narrative sections (below) and provider modules are authoritative for edge cases.
- `supports_follow_up` for Cursor means **HTTP proxy** follow-up (see `cursor_settings.py`) — **not** operator digest gating.
- `audit_sink` only lists values that exist today on `ControlPlaneProviderAuditRef` (`cursor_jsonl` / `droid_jsonl`); **planned** OpenCode has no sink in that enum yet.
- `status_mapping` and digest fields are **pointers** to code/doc names, not executable hooks.

| provider | display_name (short) | harness_family | registry_status | requires_local_root | requires_remote_repo | supports_operator_preview | supports_operator_launch | supports_status_poll | supports_follow_up | returns_stable_external_id | requires_provider_side_auth | audit_sink | digest_family (summary) | base_revision_source (summary) | status_mapping (summary) | topology_note |
|----------|----------------------|---------------:|-----------------|--------------------|--------------------|-------------------------|------------------------|--------------------|-----------------|----------------------|---------------------------|------------|------------------------|----------------------|----------------------|---------------|
| `cursor_cloud_agent` | Cursor Cloud Agent | remote_http_agent | implemented | no | **yes** | yes | yes | yes | yes (proxy) | usually (agent id) | yes (Cursor API key) | `cursor_jsonl` | `compute_cursor_proposal_digest` + `CURSOR_AGENT_BASE_REVISION` | `CURSOR_AGENT_BASE_REVISION` | `map_cursor_raw_status` | Remote GitHub; optional local mirror on CP. |
| `factory_droid` | Factory Droid | local_subprocess | implemented | **yes** | no | yes | yes | no (v1) | no | sometimes (`session_id`) | no^ | `droid_jsonl` | `compute_proposal_digest` + `REGISTRY_REVISION` | `REGISTRY_REVISION` | `droid_outcome_to_ham_status` | Local `droid exec`; `workflow_id` on CP. ^Mutating: `HAM_DROID_EXEC_TOKEN`. |
| `opencode_cli` | OpenCode CLI | local_cli_planned | **planned_candidate** | **yes** (v1 intent) | no | yes^ | yes^ | no (v1 intent) | no (v1 intent) | no (v1 intent) | yes (v1 intent) | **none in CP yet** | TBD | TBD | TBD | **Not implemented in HAM** — no `ControlPlaneProvider` value; no runtime. ^Bools in code = intended v1; `implemented` remains false. |

---

## 7. Capability matrix (Cursor vs Droid) — narrative

| Dimension | Cursor Cloud Agent | Factory Droid |
|-----------|--------------------|--------------|
| **Operator preview** | Yes — digest + pending summary (API key required for preview) | Yes — allowlisted workflow + digest |
| **Operator launch** | Yes — verify digest + HAM bearer + Cursor API | Yes — verify digest + confirm + droid policy/tokens for mutating paths |
| **Digest source** | Canonical task + repo/ref/model/PR options + `CURSOR_AGENT_BASE_REVISION` | `compute_proposal_digest` inputs + `REGISTRY_REVISION` |
| **Base revision source** | `cursor-agent-v2` (constant) | Workflow registry `REGISTRY_REVISION` |
| **external id** | Cursor **agent** id (after launch) | **session_id** from runner JSON when present |
| **Status / readback** | `GET` agent; may **update** same `ControlPlaneRun` | Primarily **terminal** mapping in launch flow (`droid_outcome_to_ham_status`); not Cursor-like poll |
| **Terminal status mapping** | `map_cursor_raw_status` | `droid_outcome_to_ham_status` |
| **Requires local project root** | No for execution (optional mirror/audit) | **Yes** |
| **Requires remote GitHub repo** | **Yes** (resolved URL) | No |
| **Follow-up / continuation** | **REST** proxies (`/api/cursor/.../followup`); **not** digest-gated in operator | Not exposed as Cursor-style follow-up in v1 |
| **Audit sink** | `cursor_jsonl` (central + optional project mirror) | `droid_jsonl` (under project `.ham/_audit/`) |
| **Topology** | Remote agent against hosted repo | Local `droid exec` on registered project root |
| **Commit token (HAM)** | `HAM_CURSOR_AGENT_LAUNCH_TOKEN` (operator) | `HAM_DROID_EXEC_TOKEN` (when workflow requires) + operator policy |

---

## 8. Common vs provider-specific

**HAM should normalize**

- `ControlPlaneRun` fields and caps (per [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md)).
- A single **mapped** lifecycle vocabulary and **`status_reason`** discipline.
- **Per-provider** digest and verify **functions** (implemented in their modules, not a fake universal hash).

**Remain provider-native**

- Cursor: HTTP shapes, repository resolution, PR/branch, follow-up routes, defensive summarization of Cursor JSON.
- Droid: registry, `droid exec` wiring, exit/session parsing, project-local audit files.

**Capability metadata (as of §6)**

- The read-only registry (see **§6** and `src/ham/harness_capabilities.py`) holds flags for UI/tests **without** a dynamic plugin system. Do not grow it into a framework.

**Explicitly deferred**

- Versioned `extensions` on `ControlPlaneRun` until a concrete need; graph/queue; adapter ABCs; coupling Hermes judgments to `ControlPlaneRun` truth.

---

## 9. Relationship to `ControlPlaneRun`

- **`ControlPlaneRun`** is the **factual, provider-neutral** durable record for **what HAM committed** and **what it last observed** under caps — authoritative **schema and semantics** are in [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md).
- **This contract** sits **above** that record: it defines **harness behavior** (what Cursor vs Droid do **before and after** a row exists, what must stay native, what capabilities exist).
- **Do not** duplicate the full `ControlPlaneRun` schema here; when in doubt, read [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) and `src/persistence/control_plane_run.py`.

---

## 10. Preservation rules / anti-patterns

| Do | Don’t |
|----|--------|
| Keep Cursor digest + verify + dual entry points (operator vs proxy) **explicit** in design | Flatten Cursor into a generic “cloud launch” and lose digest policy |
| Treat follow-up as **Cursor-only** optional surface | Assume every harness has follow-up or conversation |
| Model capabilities per harness (preview, poll, topology) | Force identical preview/launch/status **verbs and payloads** |
| State topology (local root vs remote repo) clearly | Hide constraints in a shared DTO |
| Store **capped** excerpts; **pointers** to JSONL | Stuff full provider blobs into `ControlPlaneRun` |
| Add a **third** harness before inventing a large framework | Build `HarnessAdapter` / plugin loaders **prematurely** |

---

## 11. Recommended next step

- This file remains the **authoritative** human table; `src/ham/harness_capabilities.py` is the small **read-only** mirror (keep them in lockstep in PRs that change capabilities).
- **No** runtime adapter framework until a **third** harness (or a concrete product requirement) **proves** the need. OpenCode remains **documentation + registry entry** until a separate implementation pass adds a `ControlPlaneProvider` value and workflow code.

---

## 12. Cross-references

| Document | Role |
|----------|------|
| [`docs/CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) | Durable `ControlPlaneRun` record: schema, commit boundary, caps, audit pointers. |
| [`docs/HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) | Operator/chat control plane: phases, tokens, product behavior. |
| `src/integrations/cursor_cloud_client.py` | Cursor HTTP (Bearer). |
| `src/ham/cursor_agent_workflow.py` | Cursor digest, launch, status, JSONL audit. |
| `src/api/cursor_settings.py` | Cursor proxy routes (incl. follow-up). |
| `src/ham/droid_workflows/preview_launch.py` | Droid preview/launch, CP integration. |
| `src/persistence/control_plane_run.py` | `ControlPlaneRun` model and store. |
| `src/ham/harness_capabilities.py` | Read-only capability registry (mirrors §6; no dispatch). |

---

*This document is architecture truth for the **two implemented** harnesses; §6 may list **planned** providers that are not in `ControlPlaneProvider` yet. It does not claim “full orchestration” beyond bounded control-plane behavior.*
