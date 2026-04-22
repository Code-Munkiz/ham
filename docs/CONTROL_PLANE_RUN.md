# ControlPlaneRun — architecture spec (HAM)

**See also:** [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) — harness/provider **behavior** and **capability** contract (Cursor + Droid); this file stays focused on the **factual run record** and its schema.

This document is the **v1-bounded** spec for a durable **ControlPlaneRun** record: HAM’s **provider-neutral** account of a **committed** control-plane action. It is **separate** from bridge/Hermes `.ham/runs` JSON ([`src/ham/run_persist.py`](../src/ham/run_persist.py)), from **append-only audit** JSONL, from **memory/context** systems, and from **Hermes review** artifacts. The first **file-backed** implementation lives in [`src/persistence/control_plane_run.py`](../src/persistence/control_plane_run.py), wired from [`src/ham/cursor_agent_workflow.py`](../src/ham/cursor_agent_workflow.py), [`src/ham/droid_workflows/preview_launch.py`](../src/ham/droid_workflows/preview_launch.py), and [`src/ham/chat_operator.py`](../src/ham/chat_operator.py) (v1: launches + Cursor status; no graph/queue/orchestrator).

**Core separation (restate):**

- **ControlPlaneRun** — **operational facts** HAM can defend (ids, digests, mapped lifecycle, time bounds, **small** last-seen provider status, **pointers** to native/audit data).
- **memory / `memory_heist`** — **workspace context** for prompts and operators; not orchestration state.
- **Review / `HermesReviewer`** — **judgment-shaped** text; not drivers of this record’s lifecycle, not embedded as truth by default.
- **Provider** — **authoritative** for their own execution semantics; full payloads stay **native**; this record **links** or holds **capped** excerpts only.

---

## 1. Files that informed this spec (repo)

- `docs/HAM_CHAT_CONTROL_PLANE.md` — operator intents, tokens, preview/launch/status, audit sinks
- `src/ham/cursor_agent_workflow.py` — proposal digest, base revision, launch/status, JSONL audit
- `src/ham/droid_workflows/preview_launch.py` — preview/launch results, `compute_proposal_digest`, `REGISTRY_REVISION`
- `src/ham/run_persist.py`, `src/persistence/run_store.py` — **bridge** runs + `hermes_review` (different concern)
- `src/ham/operator_audit.py` — append-only operator actions
- `src/persistence/project_store.py` — `project_id` / root
- `src/hermes_feedback.py` — advisory critic (not orchestration policy)
- `src/ham/one_shot_run.py` — bridge + review + `persist_ham_run_record` (separate path)

---

## 2. Executive thesis

HAM needs one honest “**what did we ask the provider to do, and what do we know about it?**” record. Today that is **split** across: operator `operator_result` (ephemeral), droid / Cursor domain structs, and **append-only JSONL** audits—plus **RunStore** for **bridge+Hermes** file JSON. **ControlPlaneRun** does **not** replace those; it **normalizes the minimum** HAM view: identity, project binding, **provider + action kind**, **digest/revision** used for gating, **external id** when available, **HAM status** and **time bounds** (including the **commit boundary**), a **bounded** last provider status token, and **pointers** to **native** payloads and **audit** lines. Mission graphs, queues, and **self-learning** are **out of scope** for v1.

---

## 3. Role of `ControlPlaneRun`

| Question | Answer |
|----------|--------|
| **What problem does it solve?** | A **durable, queryable** place for *which* launch (project, provider, intent), *what* was bound at **commit** (digest/revision), *what* provider id to poll, and *where* HAM is in its **own** lifecycle—without re-parsing only chat or multiple JSONL files. |
| **System of record for?** | **HAM-observed** control-plane **launches** (Droid, Cursor agent) and **subsequent** HAM-observed **status** (e.g. Cursor polls). **Not** Cursor/Droid’s full internal truth. |
| **Explicitly NOT (yet)?** | Mission graph, **parent/child** runs, **queue**, **retries** / **cancel** / **resume** as **data-plane features**, **self-learning** substrate, or storing **LLM/Hermes judgments** as **facts** that **drive** the next launch. |
| **Provider-native payloads?** | **Not** inlined as a junk drawer. **Reference** (path, audit line id) + optional **capped** excerpt fields already used elsewhere. |
| **Provider audit JSONL?** | **Link** to sinks (Cursor / Droid JSONL) + `audit_id` when present. |
| **RunStore / bridge?** | **RunStore** stays **bridge + hermes_review**; **no** overloading. Prefer a **separate** **ControlPlaneRun** store. |
| **Memory / context?** | **No** automatic writes into memory from this record. **Optional** `context_engine_revision` (hash) — **deferred** unless a concrete UI needs it. |

---

## 4. Commit boundary and timestamps (v1)

**`committed_at` (required, ISO 8601 UTC):** the instant HAM **crosses the operator-confirmed, irreversible control-plane boundary** for this run—i.e. **after** preview, when **launch** (or the first **committed** mutating request you choose to track) is **authorized** and the write path is entered with a valid digest/revision. It is **not** a preview timestamp.

**Distinction from other times:**

- **`created_at`** — when this **durable HAM record** was first **written** to the store.
- **`committed_at`** — semantic **“deal sealed”** for the control-plane action. **v1 profile:** the record is **only created post-commit** (not for preview alone), so **`created_at` and `committed_at` are often the same or within the same write transaction**; the field exists so the model stays **honest** if a future version ever persists a **draft** row.
- **`started_at`** — when the **provider** run is considered **started** from HAM’s view (e.g. launch API success, or runner start).
- **`finished_at`** — terminal HAM state reached.
- **`last_observed_at`** — last successful **poll/observation** of provider state (e.g. Cursor `GET` agent).

**Do not** conflate `committed_at` with `last_observed_at` (the latter is **reconciliation**).

---

## 5. Canonical lifecycle (HAM-native, minimal)

Create the **record** only **after** the **commit** boundary (see §4), not for preview. Previews stay in **audit** and operator flows as they do today.

| State | Meaning | Honest for Cursor / Droid today? |
|-------|---------|-----------------------------------|
| `running` | HAM has **submitted** work (launch accepted / runner going) | Yes |
| `succeeded` | Terminal **success** (mapped rules for Cursor; exit 0 for Droid) | Droid: yes. Cursor: only with **explicit** status→outcome map; else `unknown` |
| `failed` | Terminal **failure** (non-zero exit, API error, mapped failure) | Yes / partial (Cursor) |
| `unknown` | **Cannot** classify (unmapped/ambiguous status, missing observation) | **Yes** — required honesty |

**Optional `stale`:** still **deferred** (only if you persist unlaunched digests—**out of v1** by default).

**`last_provider_status` (optional, v1, bounded text):** the **last raw** status **token** or short string the provider returned (e.g. Cursor status field), **not** a full JSON blob—**max length capped** in implementation (e.g. 256–512 chars) for **debugging and mapping** without growing the record into a **dump**. Update on each successful observation that includes status.

**`dispatched` vs `running`:** **Do not** split unless you have two **independently observable** steps; v1: **one** `running` after commit.

---

## 6. Schema — v1 (first-class, bounded, no junk drawer)

**Required (v1)**

- `ham_run_id` (uuid) — HAM primary key
- `provider` — `cursor_cloud_agent` | `factory_droid` | (future, enumerated)
- `action_kind` — e.g. `launch`; status polling updates **the same** row in v1 for Cursor
- `project_id` (HAM registry)
- `committed_at` — §4
- `created_at`, `updated_at` (ISO 8601 UTC)
- `status` — §5
- `status_reason` — short, machine- or human-readable (e.g. `exit_code:1`, `unmapped_status:…`)
- `proposal_digest`, `base_revision` (from existing HAM compute/constant paths)
- `external_id` (nullable; Cursor `agent_id`, Droid `session_id` / opaque runner id)
- `workflow_id` (droid; null for cursor)
- `error_summary` (nullable, short)
- `created_by` / **actor** — align with `operator_audit` (Clerk ids where applicable) or `null` for CLI

**Optional v1 (bounded)**

- `summary` — from existing `summarize_*` **outputs** only, not new free-form LLM
- `last_provider_status` — §5

**`parent_run_id` — not in v1 schema**

- **No** graph, **no** “child run” semantics in v1. A **future** `parent_control_plane_run_id` (or equivalent) is a **post-v1, post–mission-graph** concern only; **do not** add the column/field in v1 **unless** a concrete non-graph requirement appears (default: **omit**).

**Deferred (not v1)**

- mission tags, **priority**, graph edges, embeddings, **full** review blobs
- unbounded `metadata: dict` — if needed later, use **versioned** `extensions: { "cursor" | "droid": { … } }` with **documented** keys and **size caps**

**Artifact / reference (fixed sub-shape, v1)**

- `audit` — e.g. `{ "operator_audit_id"?: str, "provider_audit": { "sink": "cursor_jsonl" | "droid_jsonl" | "project_mirror", "path"?: str } }`
- `provider_artifact` — **optional** `{ "kind", "ref" }` to a file/line—**v1** may rely on JSONL only

---

## 7. Storage strategy (v1) — **hosted first**

| Approach | Verdict |
|----------|---------|
| Reuse/extend `RunStore` / `RunRecord` for provider launches | **No** — different meaning (bridge+Hermes). |
| New **ControlPlaneRun** model + small store | **Yes**. |

**Default layout (intended to be **correct in hosted/server** environments first):**

- **Primary (default):** a **server-global** directory, e.g. `~/.ham/control_plane_runs/` (or a single `HAM_CONTROL_PLANE_RUN_DIR` / env-documented path), with **one JSON file per** `ham_run_id` and **`project_id` inside the record**. This avoids assuming a **stable, writable** per-project mount on **Cloud Run** or similar.

**Local / operator optimization (secondary):** when **`project_root`** is **resolvable, stable, and writable** (developer machine, **mounted** workspace), the implementation may **additionally** (or as an optional mirror) write under **`<project_root>/.ham/control_plane/runs/{ham_run_id}.json`**. This is a **convenience** for human inspection, **not** the only source of truth in multi-host builds.

**Implementation bias:** do **not** default to “project root only” if that is **false** in production; **global store first** keeps hosted behavior **honest**.

**Consistency:** atomic `tmp` + `replace` (same pattern as `run_persist`).

---

## 8. Provider mapping (unchanged from prior spec, condensed)

- **Droid:** create/update on launch completion path; `external_id` from `session_id` where applicable; full stdout/stderr **not** in record.
- **Cursor:** create on launch success (or `failed` row for traceability on hard failure); update on `status` poll; map API status → HAM state **or** `unknown` **honestly**.
- **Bridge + Hermes** (`launch_run`): remains **separate** `RunRecord`; **optional** future link from ControlPlaneRun **not** v1.

---

## 9. Memory / review / self-learning (crisp, unchanged intent)

- **Facts only** in lifecycle-driving fields. **No** **Hermes `ok/notes`** as the **source of truth** for `status`.
- **Context systems** may **reference** `ham_run_id` (read-only navigation).
- **Review** by **reference** to bridge run files, **not** bulk-embedded in ControlPlaneRun.
- **No** automatic “provider output → durable memory.”

---

## 10. Operator / UI implications (no code)

After launch, `operator_result` should eventually expose: `ham_run_id`, `status`, `external_id`, **short** `summary`, and **pointers** to audit—not full provider JSON.

**Do not build yet:** mission graph UI, **swarm** board, or auto re-launch from memory.

---

## 11. Risks / anti-patterns

- **Lying** on Cursor status (always map with tests or use `unknown`).
- **Junk drawer** `metadata` — use bounded **extensions** **later** if ever.
- **Optimizing** storage for **local-only** and breaking **hosted** (see §7).
- **Pretending** v1 has **orchestration** or **parent/child** because a field name exists.

---

## 12. What not to do yet (v1)

- No `parent_run_id` / **graph** in the **implemented** model.
- **No** queue, **retry** policy, **cancel** / **resume** as substrate features in this table.
- **No** full provider payload or **review** blobs in the **core** row.
- **No** FTS/learning on this table.

---

## 13. Remaining pre-coding decisions

- **Cursor** status string → HAM `succeeded` | `failed` | `unknown` table (must be **tested** against real or captured API responses).
- **Exact** path/env name for the **server-global** store in production (env var + default under `~/.ham/…`).
- **Droid** `session_id` semantics across runner versions: remain **opaque** in `external_id`.

---

**Summary:** `ControlPlaneRun` is the **first brick**—**durable, HAM-typed, commit-bounded, audit-linked**, not the whole building, **not** a **graph** or **orchestrator** in v1.
