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

## Linux packaging (Pop!_OS / Ubuntu-class)

Artifacts are built with **[electron-builder](https://www.electron.build/)**. Primary output is **AppImage** (single file, no root install). **`.deb`** is also produced for `dpkg`/Software installs.

**Why AppImage first:** one portable binary, fast iteration on Pop!_OS, no repo signing. **deb** is optional system integration for the same build.

### Prerequisites

- Node **20–24** (matches `engines` in `package.json`).
- From repo root once: `cd frontend && npm install` (the pack script builds the Vite app with `--base ./`).

### Build

```bash
cd desktop
npm install          # pulls electron-builder
npm run pack:linux   # builds ../frontend/dist, then Linux targets
```

**Outputs** (under `desktop/dist-pack/`):

| Artifact | Example (v0.1.0, x64) |
|----------|------------------------|
| AppImage | `HAM Desktop-0.1.0.AppImage` |
| deb | `ham-desktop_0.1.0_amd64.deb` |

The AppImage name includes a space (from `productName`). The `.deb` requires `homepage` in `desktop/package.json` (used by the Debian metadata step).

**Faster unpack-only smoke build** (no installer wrappers):

```bash
cd desktop && npm run pack:linux:dir
```

Unpacked app: `desktop/dist-pack/linux-unpacked/` (run the `ham-desktop` or `HAM Desktop` binary inside).

### Run / install on Pop!_OS

**AppImage**

```bash
chmod +x "./HAM Desktop-"*.AppImage
HAM_DESKTOP_API_BASE=http://127.0.0.1:8000 "./HAM Desktop-"*.AppImage
```

(AppImage may need [FUSE](https://docs.appimage.org/user-guide/troubleshooting/fuse.html) on minimal systems; Pop!_OS normally has it.)

**AppImage: Chromium sandbox / launch failures**

Some Linux setups block the setuid sandbox inside the AppImage (kernel/user namespace policy, older FUSE setups, or unusual mounts). If the window never appears or the process exits with sandbox-related errors, try launching with Chromium’s troubleshooting flag (reduces sandboxing — use only when needed):

```bash
./"HAM Desktop-0.1.0.AppImage" --no-sandbox
```

This does not change HAM’s renderer security model (`contextIsolation` / no `nodeIntegration`); it relaxes the **Chromium** process sandbox for that run. Prefer fixing host configuration when possible; keep this as an operator fallback.

**deb**

```bash
sudo apt install ./ham-desktop_*_amd64.deb
# Application menu: "HAM Desktop", or from a terminal:
"/opt/HAM Desktop/ham-desktop"
```

(Install path is under `/opt/HAM Desktop/`; quote the path because of the space.)

Packaged builds default to **`file` load mode** and load the bundled renderer from `resources/renderer/`. **Runtime API base** is unchanged: set `HAM_DESKTOP_API_BASE` when launching, or create a `ham-desktop-config.json` under Electron’s `userData` directory (on Linux often `~/.config/HAM Desktop/`) with `{"apiBase":"http://127.0.0.1:8000"}`. Without `apiBase`, the production frontend will error until configured (same as a static web build without `VITE_HAM_API_BASE`).

### Packaged app and CORS (`Origin: null`)

The packaged UI is loaded from **`file://`** (local HTML/JS under `resources/renderer/`). When the dashboard calls your Ham API over HTTP (`fetch` to `HAM_DESKTOP_API_BASE`), browsers send:

```http
Origin: null
```

That is normal for `file://` pages; it is **not** the string `"file://"`. The FastAPI app must allow this origin or the browser will block responses (**“Failed to fetch”** in DevTools with a CORS error, often with `null` in the message).

**Configure the API** (see [`src/api/server.py`](../src/api/server.py) — `HAM_CORS_ORIGINS` / `HAM_CORS_ORIGIN_REGEX`):

1. Include the literal token **`null`** in the comma-separated **`HAM_CORS_ORIGINS`** list (alongside any real origins you still need, e.g. Vite or Vercel):

   ```bash
   export HAM_CORS_ORIGINS="http://127.0.0.1:3000,http://localhost:3000,null"
   ```

2. Restart `uvicorn` (or redeploy Cloud Run) so the new env is picked up.

If you only set `HAM_CORS_ORIGINS` to `http` origins and omit `null`, **packaged desktop will not be able to talk to the API** even when `HAM_DESKTOP_API_BASE` is correct. Dev workflow (`http://127.0.0.1:3000` + Vite proxy) does not hit this path.

### CI / clean builds

- `desktop/dist-pack/` is gitignored; delete it between releases if needed.
- Bump `version` in `desktop/package.json` when cutting a new artifact.

## Environment reference

| Variable | Purpose |
|----------|---------|
| `HAM_DESKTOP_DEV_SERVER_URL` | URL to load in `devserver` mode (default `http://127.0.0.1:3000`) |
| `HAM_DESKTOP_LOAD_MODE` | `devserver` (default) or `file` |
| `HAM_DESKTOP_WEB_ROOT` | Directory containing `index.html` for `file` mode (default `../frontend/dist`) |
| `HAM_DESKTOP_API_BASE` | Ham API origin for runtime `getApiBase()` |
| `HAM_DESKTOP_USE_HASH_ROUTER` | `1` / `true` to force HashRouter (usually auto for `file` mode) |
