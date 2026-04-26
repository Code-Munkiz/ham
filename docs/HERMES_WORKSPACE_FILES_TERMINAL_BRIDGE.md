# Hermes Workspace — Files and Terminal HAM bridge

Bridge table (UI remains on `workspaceFileAdapter` / `workspaceTerminalAdapter`):

| Surface | Adapter call | HAM endpoint | Implementation | Data shape | Risk / follow-up |
|--------|--------------|-------------|----------------|------------|------------------|
| List tree | `listFiles` | `GET /api/workspace/files?action=list` | `src/api/workspace_files.py` | `{ entries: FileEntry[] }` | RBAC, audit, workspace root policy, path allowlist |
| Read | `readFile` | `GET /api/workspace/files?action=read&path=` | `workspace_files` | `{ content, path }` (read uses `text` in some code paths; adapter normalizes) | Encoding, max size, symlink policy |
| Write | `writeFile` | `POST /api/workspace/files` JSON `action: write` | `workspace_files` | body: path, content | Quotas, binary vs text |
| Mkdir / delete / rename | `mkdir`, `delete`, `rename` | `POST /api/workspace/files` | `workspace_files` | `action: mkdir \| delete \| rename`, `from` for rename (alias) | Cross-volume moves |
| Download | `downloadFile` | `GET` download action (see `workspace_files.py`) | `workspace_files` | `FileResponse` or buffer | Malware scan, size caps |
| Upload | `uploadFile` | `POST /api/workspace/files/upload` | `workspace_files` | `multipart` | Same as write + MIME |
| Terminal create | `createSession` | `POST /api/workspace/terminal/sessions` | `workspace_terminal` | `{ sessionId }` | Process limits, no PTY yet |
| Input | `sendInput` | `POST /api/workspace/terminal/sessions/{id}/input` | `workspace_terminal` | `{ data }` (UTF-8, `\x03` for interrupt) | Injection, rate limits |
| Output | `pollOutput` | `GET /api/workspace/terminal/sessions/{id}/output?after=` | `workspace_terminal` | `{ text, len, next }` | Polling load; consider SSE/WS |
| Resize | `resize` | `POST /api/workspace/terminal/sessions/{id}/resize` | `workspace_terminal` (no-op today) | `{ cols, rows }` | Real TTY/pty |
| Close | `closeSession` | `DELETE /api/workspace/terminal/sessions/{id}` | `workspace_terminal` | 204 | Reaper, zombie cleanup |

**Settings IA:** Mobile and shell should use `/workspace/settings` (wraps `UnifiedSettings`) — not legacy `/settings` as the final home.

**Hardening (not blocking bridge):** RBAC, audit logging, workspace root and path policy, process isolation, org/user policy, kill switch.

**Browser:** No API keys or privileged credentials in client bundles; use HAM FastAPI only; no `/api/hermes-proxy`.
