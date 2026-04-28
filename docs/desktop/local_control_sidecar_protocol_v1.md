# HAM Desktop — Local Control sidecar protocol (v1, design)

**Status:** Phase **3B** — **inert process shell shipped** (stdio JSON-line requests; methods `health`, `status`, `shutdown` only). **No** tools, **no** inbound listener, **no** automation. Start remains **blocked** while the kill switch is engaged (default).  
**Product:** Desktop-only (Electron main + local child). Not Cloud Run, not `/api/browser` as the desktop control plane, not War Room.  
**Parent:** [`local_control_v1.md`](local_control_v1.md).

---

## Purpose

Define the contract for a **local child process** (“sidecar”) that can eventually hold **risky I/O** under **Electron main** policy. **Phase 3B** implements only an **inert** lifecycle shell: spawn/stop, health ping, and read-only status echo — capabilities stay **`not_implemented`**.

---

## Design constraints (non-negotiables)

| Constraint | Meaning |
|------------|---------|
| **Main owns policy** | Kill switch, audit policy, and lifecycle remain in Electron **main**; sidecar obeys start/stop gates from main. |
| **No inbound network by default** | Sidecar does not open a listening port; transport is **stdio** to the parent process. |
| **No secrets in renderer** | Preload exposes **narrow** methods only; no generic IPC; no path/env dumps to the renderer (no child PID in status). |
| **Droid / API decoupled** | Ham API and Droid **do not** invoke the sidecar; `droid_access: not_enabled`. |
| **Default deny** | Start is **blocked** while `kill_switch.engaged` (Phase 2 policy default). |

---

## Transport (Phase 3B): stdio + JSON lines

- **Transport:** OS pipe to a **child process** spawned by **main** only (`stdin`/`stdout`).
- **Framing:** one JSON object per line (newline-delimited).
- **Request:** `{ "method": "health" | "status" | "shutdown", "id"?: <string|number> }`.
- **Response:** `{ "ok": true|false, "id": ..., "method": ..., "result"? | "error"? }`.
- **Unknown `method`:** `ok: false`, `error: method_not_allowed` — no arbitrary RPC surface.

Implementation: `desktop/local_control_sidecar_child.cjs` (child), `desktop/local_control_sidecar_manager.cjs` (main).

---

## Lifecycle (Phase 3B)

1. **Main** reads policy; if kill switch engaged, **start** returns `{ ok: false, blocked: true, reason: "kill_switch_engaged" }` (no spawn).
2. **Main** spawns child with fixed argv: `process.execPath` + path to `local_control_sidecar_child.cjs` (packaged: under app asar); **`ELECTRON_RUN_AS_NODE=1`** when running under Electron so the binary behaves as Node for the child entry.
3. **Handshake:** main sends `health` after spawn; failure tears down the child.
4. **Shutdown:** main sends `shutdown`; child exits `0`. Stop is **idempotent** when not running.
5. **App quit:** `before-quit` requests stop (best-effort).

---

## Method namespace (Phase 3B)

| Method | Role |
|--------|------|
| `health` | Liveness; no I/O; returns `{ status: "ok", inert: true }`. |
| `status` | Read-only echo: `inert_process_shell`, `capabilities` all `not_implemented`. |
| `shutdown` | Clean exit; child terminates after ack. |

No `execute`, `shell`, `browser`, `fs`, or MCP methods.

---

## Browser control (historic Phase 4A/4B — removed)

Electron **managed browser** stacks (embedded `BrowserWindow` MVP, real Chromium + CDP IPC) were **removed** from this repository. Browser automation for operators uses the **Ham API** **`/api/browser*`** surface ([`computer_control_pack_v1.md`](../capabilities/computer_control_pack_v1.md)).

**Reserved namespace (future):** a Playwright-backed sidecar *could* expose allowlisted logical methods over stdio — **not** implemented here.

---

## Relationship to aggregate status

HAM Desktop exposes **`sidecar`** on the aggregate Local Control status object (**`schema_version` current: 7 for policy/sidecar bundles**), **`implemented: true`**, **`mode: inert_process_shell`**, **`transport: stdio_json_rpc`**, plus **`start_allowed`**, **`blocked_reason`**, and **`health`**. See `desktop/local_control_sidecar_status.cjs`. Aggregate status **no longer carries** `browser_mvp` / `browser_real` snapshots — see `desktop/local_control_status.cjs`.

---

## References

- [`local_control_v1.md`](local_control_v1.md) — product phases and boundaries.
- [`desktop/README.md`](../../desktop/README.md) — Electron shell and IPC inventory.
