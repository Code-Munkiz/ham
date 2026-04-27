# HAM Desktop — Local Control sidecar protocol (v1, design)

**Status:** Phase 3A — **specification and mock status only**. No shipped sidecar binary, no `child_process.spawn` for sidecar, no live JSON-RPC on stdio in this milestone.  
**Product:** Desktop-only (Electron main + future local child). Not Cloud Run, not `/api/browser` as the desktop control plane, not War Room.  
**Parent:** [`local_control_v1.md`](local_control_v1.md).

---

## Purpose

Define a **future** contract for a **local child process** (“sidecar”) that could hold **risky I/O** (browser automation, broad filesystem, shell, etc.) under **Electron main** policy, while the **renderer stays sandboxed**. This document is **normative for intent only** until a later phase explicitly implements transport and handshake.

---

## Design constraints (non-negotiables)

| Constraint | Meaning |
|------------|---------|
| **Main owns policy** | Kill switch, consent, audit policy, and lifecycle remain in Electron **main**; sidecar obeys caps from main. |
| **No inbound network by default** | Sidecar must not open a listening port for arbitrary peers; any future transport is **outbound / local** to the host. |
| **No secrets in renderer** | Preload exposes **narrow** methods only; no generic IPC; no path/env dumps to the renderer. |
| **Droid / API decoupled** | Factory Droid, Cursor, and Ham API **do not** invoke sidecar in Phase 3A; `droid_access: not_enabled` in mock status. |
| **Default deny** | Local Control and sidecar capabilities stay **off** until explicitly phased; mock status reports `not_implemented`. |

---

## Transport (planned): stdio + JSON-RPC

**Planned** framing (not implemented in 3A):

- **Transport:** OS pipe to a **child process** spawned by **main** only (stdin/stdout or equivalent).
- **Message shape:** JSON-RPC 2.0–style requests/responses (single line per message or length-prefixed — **TBD** at implementation time).
- **Version field:** Every request/response should carry a **`protocol_version`** or method namespace (e.g. `ham.sidecar.v1.*`) so main and sidecar can refuse mismatched peers.

No WebSocket, no HTTP server inside the sidecar for Phase-1 implementation of this protocol unless explicitly approved later.

---

## Lifecycle (conceptual)

1. **Main** evaluates policy + kill switch; if disallowed, **never** spawn sidecar.
2. **Main** spawns sidecar with fixed argv (allowlisted); no free-form user argv from renderer.
3. **Handshake:** sidecar sends `ready` / capability advertisement **bounded** by main’s policy (future).
4. **Operation:** main forwards **narrow** requests; sidecar returns **redacted** results (no raw env, no unrestricted paths in IPC to renderer).
5. **Shutdown:** main kills child on kill-switch or app quit; sidecar must not survive as orphan automation.

Phase 3A implements **none** of the above in code — only **mock** `running: false` status.

---

## Method namespace (placeholder)

Future methods might include namespaced RPC such as:

- `ham.sidecar.v1.ping` — health (no I/O)
- `ham.sidecar.v1.capabilities` — read-only capability echo under policy

**Phase 3A:** no methods registered; documentation only.

---

## Relationship to aggregate status

HAM Desktop exposes **`sidecar`** on the aggregate Local Control status object (`buildLocalControlStatus`) with **`mode: mock_status_only`** until a real child exists. See `desktop/local_control_sidecar_status.cjs`.

---

## References

- [`local_control_v1.md`](local_control_v1.md) — product phases and boundaries.
- [`desktop/README.md`](../../desktop/README.md) — Electron shell and IPC inventory.
