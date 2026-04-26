# Hermes Workspace — Files and Terminal HAM bridge

**Local Files mode:** the Files API reads/writes a directory on the **same machine** as the FastAPI
process. Set `HAM_WORKSPACE_ROOT` to your local folder; legacy `HAM_WORKSPACE_FILES_ROOT` is still
honored. For real local project trees, run the Vite app with its dev proxy to a **local** API; a
browser pointed only at a remote deploy will not see your laptop’s files.

**Dev proxy (common pitfall):** Vite proxies `/api/*` to `VITE_HAM_API_PROXY_TARGET` (default
`http://127.0.0.1:8000` — see `frontend/vite.config.ts` and `frontend/.env.example`). If your HAM
`uvicorn` runs on another port (e.g. 8001), set the variable in **`frontend/.env.local`** to that
origin and **restart Vite**; otherwise `GET /api/workspace/files?action=list` may 404 and the Files
UI shows “Runtime bridge pending” even when the correct API on the other port works in isolation.
**Do not commit** `.env.local` (it is gitignored); copy from `.env.example` as needed.

Bridge table (UI remains on `workspaceFileAdapter` / `workspaceTerminalAdapter`):

| Surface | Adapter call | HAM endpoint | Implementation | Data shape | Risk / follow-up |
|--------|--------------|-------------|----------------|------------|------------------|
| List tree | `listFiles` | `GET /api/workspace/files?action=list` | `src/api/workspace_files.py` | `{ entries: FileEntry[] }` | RBAC, audit, workspace root policy, path allowlist |
| Read | `readFile` | `GET /api/workspace/files?action=read&path=` | `workspace_files` | `{ content, path }` (read uses `text` in some code paths; adapter normalizes) | Encoding, max size, symlink policy |
| Write | `writeFile` | `POST /api/workspace/files` JSON `action: write` | `workspace_files` | body: path, content | Quotas, binary vs text |
| Mkdir / delete / rename | `mkdir`, `delete`, `rename` | `POST /api/workspace/files` | `workspace_files` | `action: mkdir \| delete \| rename`, `from` for rename (alias) | Cross-volume moves |
| Download | `downloadFile` | `GET` download action (see `workspace_files.py`) | `workspace_files` | `FileResponse` or buffer | Malware scan, size caps |
| Upload | `uploadFile` | `POST /api/workspace/files/upload` | `workspace_files` | `multipart` | Same as write + MIME |
| Terminal create | `createSession` | `POST /api/workspace/terminal/sessions` | `workspace_terminal` | `{ sessionId, transport, streamPath }` (optional JSON `cols`/`rows`) | Win: `pywinpty` ConPTY when `HAM_TERMINAL_PTY` not `0` |
| Input | `sendInput` | `POST /api/workspace/terminal/sessions/{id}/input` | `workspace_terminal` | `{ data }` (UTF-8, `\x03` for interrupt) | Injection, rate limits |
| Output (poll) | `pollOutput` | `GET /api/workspace/terminal/sessions/{id}/output?after=` | `workspace_terminal` | `{ text, len, next }` | Fallback and tests; `read1` on pipe child |
| Output (stream) | (WS URL from `webSocketStreamUrl`) | `WebSocket` `/api/workspace/terminal/sessions/{id}/stream` | `workspace_terminal` | JSON `{"type":"out","text"}`; optional in/out `resize` | Vite: `server.proxy["/api"].ws: true` |
| Resize | `resize` | `POST /api/workspace/terminal/sessions/{id}/resize` | `workspace_terminal` | `{ cols, rows }` | ConPTY: `setwinsize`; pipe: no-op |
| Close | `closeSession` | `DELETE /api/workspace/terminal/sessions/{id}` | `workspace_terminal` | 204 | Idle: `HAM_TERMINAL_IDLE_SECONDS` reaper; multi-process API still N/A for shared memory |

**Settings IA:** Mobile and shell should use `/workspace/settings` (wraps `UnifiedSettings`) — not legacy `/settings` as the final home.

**Hardening (not blocking bridge):** RBAC, audit logging, workspace root and path policy, process isolation, org/user policy, kill switch.

**Design details / roadmap:** see [`TERMINAL_PTY_PARITY.md`](./TERMINAL_PTY_PARITY.md).

**Pipe bridge (Windows) reader:** the pipe-fallback path still uses `read1` on the child `stdout` (see `workspace_terminal`); the ConPTY path reads `PtyProcess.read()` in a thread.

**Env:** `HAM_TERMINAL_PTY=0` forces pipe+read1 on Windows. `HAM_TERMINAL_IDLE_SECONDS` (default 3600) idles reaped. Shell `cwd` uses `HAM_WORKSPACE_ROOT` / `HAM_WORKSPACE_FILES_ROOT` when set.

**Browser:** No API keys or privileged credentials in client bundles; use HAM FastAPI only; no `/api/hermes-proxy`.
