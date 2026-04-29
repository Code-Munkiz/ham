# Terminal PTY / streaming parity (Hermes Workspace)

**Purpose:** Design reference for moving `/workspace/terminal` from a pipe/poll bridge toward Hermes-style terminal behavior. This doc is the source of truth for capability tradeoffs; implementation status is updated in `HERMES_WORKSPACE_FILES_TERMINAL_BRIDGE.md` as the bridge ships.

**Runtime rule (unchanged):** Terminal runs in the local HAM API process. No browser-side secrets; no direct browser-to-upstream-Hermes/Cursor routes.

## Design table

| # | Capability | Current behavior (pre-slice) | Target behavior | Implementation option | Files impacted | Risk / notes |
|---|------------|----------------------------|-----------------|------------------------|----------------|--------------|
| 1 | PTY support | `subprocess` pipes to `cmd` / shell; `read1` for Windows | **Win:** ConPTY via `pywinpty`. **Unix:** real TTY/pty in a follow-up (fork-in-threaded-server is unsafe; needs subprocess worker or pty-based helper) | `pywinpty` on `nt`, optional `HAM_TERMINAL_PTY=0` to force pipe; Unix stays pipe until worker design | `src/api/workspace_terminal.py`, `requirements.txt` | `pywinpty` adds a native dep; import guarded on non-Windows |
| 2 | Resize | No-op; HTTP 200 | **PTY:** `setwinsize` / `PtyProcess.setwinsize`. **Pipe:** still no-op | `resize` calls backend `set_winsize` when `kind=="pty"` | `workspace_terminal.py`, `terminalAdapter.ts`, `WorkspaceTerminalView.tsx` | Trivial on Win PTY; pipe documented |
| 3 | Output streaming | HTTP `GET /output?after=` | **Primary:** `WebSocket` push of output deltas. **Fallback:** same HTTP poll for tests / no-WS | `WS /api/workspace/terminal/sessions/{id}/stream` JSON `{"type":"out","text"}`; HTTP retained | `workspace_terminal.py`, `terminalAdapter.ts`, `WorkspaceTerminalView.tsx` | Must not duplicate secrets; re-use session table |
| 4 | Input handling | `POST /input` JSON `data` | **WS** `{"type":"in","data"}`; **HTTP** unchanged | `write()` on Win PTY (str) or pipe stdin (bytes) | same | `pywinpty` expects `str` writes |
| 5 | Ctrl+C / interrupt | `\\x03` in input | Same bytes to TTY/PTY; shell interprets | Unchanged; PTY path forwards raw string | `MobileTerminalInputBar`, `WorkspaceTerminalView` | Some shells need raw mode; acceptable for slice |
| 6 | Session lifecycle | In-memory; `DELETE` closes | Same + **idle timeout** + reaper; explicit delete | Background thread + `last_touched` on I/O/WS | `workspace_terminal.py` | Multi-worker still not supported; document |
| 7 | Cleanup (close/refresh) | `DELETE` on tab close | **WS** disconnect does not always kill — caller should `DELETE` or rely on reaper; optional `beforeunload` later | `HAM_TERMINAL_IDLE_SECONDS` (default 3600) | frontend optional follow-up | `sendBeacon` is best-effort |
| 8 | Multi-tab | One session per tab; independent UUIDs | Same; no change | N/A (product UI) | `WorkspaceTerminalView.tsx` | None |
| 9 | Single-worker assumption | Documented | Still in-memory; **not** a long-term “won’t fix” | Future: external session store or sticky sessions; out of this slice | docs | — |
| 10 | Windows vs Unix | Win cmd / Unix bash `-i` | **Win:** ConPTY. **Unix:** pipe until pty worker exists | `os.name` branches | `workspace_terminal.py` | Unix pty = separate milestone |

## Phased execution

1. **Shipped in repo (this pass):** Windows ConPTY via `pywinpty`, WebSocket `/sessions/{id}/stream` (JSON) + HTTP `GET /output` fallback, `resize` applied on ConPTY, idle reaper (`HAM_TERMINAL_IDLE_SECONDS`), Vite `ws: true` for the API proxy, design doc + bridge doc updates, UI opens WebSocket and disables HTTP poll when the socket is up.
2. **Next:** Unix pty without `fork` in threaded parent (dedicated process or vetted `ptyprocess` pattern), then cloud/remote (out of scope here).

## Dependency

- **`pywinpty`** (ConPTY on Windows, MIT) — used only when `os.name == "nt"` and `HAM_TERMINAL_PTY` is not `0`.

## Manual smoke (local)

See `HERMES_WORKSPACE_FILES_TERMINAL_BRIDGE.md` and run `/workspace/terminal` with Vite + local API: prompt, `echo`, `^C`, resize, new tab, Files + chat unchanged.
