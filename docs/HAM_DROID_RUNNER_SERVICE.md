# HAM Droid Runner service (inbound HTTP)

Minimal **single-endpoint** service that executes Factory **`droid exec`** on a **runner host** where `droid` and **`FACTORY_API_KEY`** (or equivalent) are available. Ham’s main API talks to it via **`src/integrations/droid_runner_client.py`** when **`HAM_DROID_RUNNER_URL`** is set.

## When to use this

| Mode | Who runs `droid` |
|------|------------------|
| **Local** | Ham API process (`HAM_DROID_RUNNER_URL` unset) |
| **Remote** | This runner process on a VM/sidecar co-located with the repo + Factory auth |

The runner does **not** replace Ham policy: workflow allowlists, preview/digest, and mutating **`HAM_DROID_EXEC_TOKEN`** gates remain on the **Ham API**. The runner only validates argv defensively and runs subprocess **`shell=False`**.

## Auth (runner host)

| Variable | Purpose |
|----------|---------|
| **`HAM_DROID_RUNNER_SERVICE_TOKEN`** | **Required.** Shared secret; inbound requests must send `Authorization: Bearer <same value>`. |

On the **Ham API** host, set **`HAM_DROID_RUNNER_TOKEN`** to the **same secret** so `droid_runner_client` can authenticate. The names differ so it is obvious which process owns which role.

**Never** put **`FACTORY_API_KEY`** in Ham API env for this path; it stays **only** on the runner (and is never read from the HTTP request body).

## Allowed roots (production)

| Variable | Purpose |
|----------|---------|
| **`HAM_DROID_RUNNER_ALLOWED_ROOTS`** | Optional but **strongly recommended** in production: comma-separated **absolute** directory paths. After `Path(cwd).expanduser().resolve()`, the cwd must be **exactly** one of these roots or a subdirectory (`Path.relative_to` containment). Symlinks are followed during resolution, so a path under an allowed tree that resolves **outside** all roots is rejected (**`422` `CWD_NOT_ALLOWED`**). |
| Unset / empty | No cwd containment check (development only). |

Use one entry per workspace parent (e.g. `/srv/ham-workspaces`) or list a small set of mount points. **Relative** entries in the list are ignored.

## Runner audit log (JSONL)

| Variable | Purpose |
|----------|---------|
| **`HAM_DROID_RUNNER_AUDIT_FILE`** | Append-only JSONL path (default: **`~/.ham/droid_runner_audit.jsonl`**). Parent dirs are created on first write. |

Each line is one JSON object. **No** bearer tokens, **no** full argv, **no** stdout/stderr (avoids leaking prompts and Factory output). Typical fields:

- `logged_at`, `runner_request_id` (per request, always)
- `status`: `blocked` | `executed`
- `cwd_requested`, `cwd_normalized`
- Optional correlation from Ham: `workflow_id`, `project_id`, `session_id`, `proposal_digest`, `ham_audit_id` (maps request `audit_id`)
- When `status` is `blocked`: `blocked_code`, `blocked_reason`
- When `status` is `executed`: `exit_code`, `duration_ms`, `timed_out`, `execution_ok`, `failure_kind` (`timeout` \| `non_zero_exit` when not ok)

Auth failures (**401** / **403** / **503**) do **not** write audit lines (noise / abuse).

## Multiple runner instances

- Use the **same** `HAM_DROID_RUNNER_ALLOWED_ROOTS` policy on every replica that serves the same Ham deployment, or partition workspaces per instance with different allowlists and different Ham `HAM_DROID_RUNNER_URL`s.
- Prefer **one audit file per runner VM** (`HAM_DROID_RUNNER_AUDIT_FILE` on local disk) or ship JSONL to centralized logging; **avoid** NFS append from many hosts without a proper log shipper (file locking / ordering).
- Keep **`HAM_DROID_RUNNER_SERVICE_TOKEN`** synchronized with Ham’s **`HAM_DROID_RUNNER_TOKEN`** for that URL; rotate both together.

## Run

```bash
export HAM_DROID_RUNNER_SERVICE_TOKEN="$(openssl rand -hex 32)"
# FACTORY_API_KEY must be available to the droid CLI in this environment.
python -m uvicorn src.ham.droid_runner.service:app --host 0.0.0.0 --port 8791
```

Or:

```bash
python -m src.ham.droid_runner
```

Optional: **`HAM_DROID_RUNNER_HOST`**, **`HAM_DROID_RUNNER_PORT`** for the `__main__` entry.

Point Ham at the runner:

```bash
export HAM_DROID_RUNNER_URL=http://<runner-host>:8791
export HAM_DROID_RUNNER_TOKEN=<same as HAM_DROID_RUNNER_SERVICE_TOKEN>
```

## API

### `POST /v1/ham/droid-exec`

**Headers**

- `Content-Type: application/json`
- `Authorization: Bearer <HAM_DROID_RUNNER_SERVICE_TOKEN>`

**Body (JSON only — no shell field)**

| Field | Type | Description |
|-------|------|-------------|
| `argv` | `string[]` | Full argv for subprocess; must pass runner validation (see Safety). |
| `cwd` | `string` | Working directory; must exist on the runner and match the `--cwd` pair inside `argv`. |
| `timeout_sec` | `int` | 1–3600; subprocess timeout. |
| `workflow_id` | `string` (optional) | Correlation; logged and echoed. |
| `audit_id` | `string` (optional) | Ham-issued id for this run (same value written to project `droid_exec.jsonl`); logged as `ham_audit_id`, echoed as `audit_id`. |
| `session_id` | `string` (optional) | Correlation; logged and echoed when provided. |
| `project_id` | `string` (optional) | Correlation; logged and echoed when provided. |
| `proposal_digest` | `string` (optional) | Correlation; logged and echoed when provided. |

**Success (HTTP 200)**

JSON object with fields consumed by `droid_runner_client._run_remote`:

- `argv`, `working_dir`, `exit_code`, `timed_out`, `stdout`, `stderr`,
- `stdout_truncated`, `stderr_truncated`, `started_at`, `ended_at`, `duration_ms`
- **`runner_request_id`** — runner-generated id for this HTTP request (always present).
- Optional metadata echoed when the request included them: `workflow_id`, `audit_id`, `session_id`, `project_id`, `proposal_digest`.

Optional (observability): **`parsed_stdout`** — present when `stdout` parses as a JSON **object**.

Non-zero **`exit_code`** or timeout still returns **HTTP 200** with an honest structured body (Ham records failure downstream).

**Errors**

| HTTP | Meaning |
|------|---------|
| 401 | Missing or non-Bearer `Authorization` |
| 403 | Wrong bearer token |
| 503 | `HAM_DROID_RUNNER_SERVICE_TOKEN` not set on runner |
| 422 | Bad `cwd`, argv failed validation, or **cwd not under** `HAM_DROID_RUNNER_ALLOWED_ROOTS` (`CWD_NOT_ALLOWED`) |

## Safety model

1. **No arbitrary shell** — the body has no command string; only `argv` + `cwd` + timeout.
2. **Allowed roots** — when configured, resolved cwd must stay under an allowed root (stops traversal / symlink escape after `resolve()`).
3. **Defensive argv rules** (`src/ham/droid_runner/argv_validate.py`):
   - `argv[0]` must be exactly `droid`; `argv[1]` must be `exec`.
   - Only allowlisted flags before the final prompt: `--cwd`, `--output-format`, `--auto`, `--disabled-tools`.
   - `--output-format` value must be `json`; `--auto` value must be `low`.
   - `--cwd` in argv must resolve to the same path as request `cwd`.
   - Forbidden tokens include **`--skip-permissions-unsafe`** (exact match anywhere in argv).
4. **Subprocess** — `shell=False`, bounded stdout/stderr caps (same order of magnitude as the local executor).
5. **Trust boundary** — Ham should only send argv built from **`src/ham/droid_workflows/`**; the runner still enforces the above in case the API is compromised or mis-wired.

## Differences from local mode

| Aspect | Local (`droid_runner_client` without URL) | Remote runner |
|--------|-------------------------------------------|---------------|
| Process | Ham API invokes `droid_executor` | Runner invokes `droid_executor` |
| Factory secrets | On API host | On runner host only |
| Network | None | TLS/reverse-proxy recommended in production |
| Validation | Ham builds argv; subprocess is local | Same argv + **runner-side validation** + optional **allowed roots** |
| Audit | Ham project `.ham/_audit/droid_exec.jsonl` only | Same Ham audit **plus** optional **runner JSONL** (`HAM_DROID_RUNNER_AUDIT_FILE`) |
| Metadata | N/A | Ham may send `workflow_id`, `audit_id`, `project_id`, `proposal_digest`; runner logs and echoes |

## Deployment notes

- Place the runner on a host that can **`cd`** to registered project roots (NFS bind, same volume, or synced workspace).
- Terminate TLS at your edge; keep the bearer token out of logs.
- No job queue, streaming, or multi-tenant “run on arbitrary machine” API — one request, one subprocess, one response.

See also **`docs/FACTORY_DROID_CONTRACT.md`**.
