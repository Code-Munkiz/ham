# HAM Desktop (Electron, Milestone 1)

Thin shell: renderer is the existing Vite/React app; FastAPI stays a separate HTTP service.

## Security (M1)

- Main: window lifecycle, reads optional `userData/ham-desktop-config.json`, merges env.
- Preload: `contextBridge.exposeInMainWorld('__HAM_DESKTOP_CONFIG__', …)` only — no Node in the renderer (`nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`).
- Phase 2 (local capability host) extends this seam — do not add filesystem/process IPC without review.

## Runtime API base

Resolve order in the renderer ([`getApiBase()`](../frontend/src/lib/ham/api.ts)):

1. Non-empty `window.__HAM_DESKTOP_CONFIG__.apiBase` (injected before the app runs).
2. Build-time `VITE_HAM_API_BASE` (web / static builds).
3. Dev: `""` → same-origin `/api/*` (Vite proxy).

Shell-side sources (merged in main, passed to preload via sync IPC):

- `HAM_DESKTOP_API_BASE` — non-empty forces absolute API origin (local, staging, or prod).
- `userData/ham-desktop-config.json` — optional `{"apiBase":"https://…"}` (see Electron `app.getPath('userData')` on your OS).
- Env wins over file for `apiBase`.

## Linux dev workflow (recommended)

Terminal 1 — API:

```bash
cd /path/to/ham
uvicorn src.api.server:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — Vite (proxy `/api` → 8000 by default):

```bash
cd frontend
BROWSER=none npm run dev
```

Terminal 3 — Electron (loads `http://127.0.0.1:3000`, uses Vite proxy if you leave `HAM_DESKTOP_API_BASE` unset):

```bash
cd desktop
npm install   # once
npm start
```

### Direct API URL (no Vite proxy)

```bash
HAM_DESKTOP_API_BASE=http://127.0.0.1:8000 npm start
```

Ensure [`HAM_CORS_ORIGINS`](../src/api/server.py) / defaults include the Vite origin you use (e.g. `http://127.0.0.1:3000`).

## Optional: `file` load mode

For packaged-style testing without the dev server:

1. Build the frontend with a **relative** asset base (required for `file://`):

   ```bash
   cd frontend && npm run build -- --base ./
   ```

2. Run Electron:

   ```bash
   cd desktop
   HAM_DESKTOP_LOAD_MODE=file \
   HAM_DESKTOP_API_BASE=http://127.0.0.1:8000 \
   HAM_DESKTOP_WEB_ROOT=../frontend/dist \
   npm start
   ```

Main sets `useHashRouter` for `file` loads so client-side routes work.

## Environment reference

| Variable | Purpose |
|----------|---------|
| `HAM_DESKTOP_DEV_SERVER_URL` | URL to load in `devserver` mode (default `http://127.0.0.1:3000`) |
| `HAM_DESKTOP_LOAD_MODE` | `devserver` (default) or `file` |
| `HAM_DESKTOP_WEB_ROOT` | Directory containing `index.html` for `file` mode (default `../frontend/dist`) |
| `HAM_DESKTOP_API_BASE` | Ham API origin for runtime `getApiBase()` |
| `HAM_DESKTOP_USE_HASH_ROUTER` | `1` / `true` to force HashRouter (usually auto for `file` mode) |
