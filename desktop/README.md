# HAM Desktop (Electron, Milestone 1)

Thin shell: renderer is the existing Vite/React app; FastAPI stays a separate HTTP service.

## Shell UX (M1)

- **First screen:** the packaged app **opens the workspace app** with **`/` → `/chat`** (workspace chat). The marketing landing (“go ham” / astrochimp) is **web-only**.
- **Local Control (desktop):** narrow IPC (`ham-desktop:local-control-*`) + **`window.hamDesktop.localControl`** for status, policy, audit/kill-switch, and inert sidecar lifecycle (**no packaged managed-browser / localhost CDP in the Electron shell**; use Ham **`/api/browser*`** on the API host instead). **`policy.json` schema v3** + redacted audit JSONL under userData; **default deny** — [`docs/desktop/local_control_v1.md`](../docs/desktop/local_control_v1.md), sidecar protocol [`docs/desktop/local_control_sidecar_protocol_v1.md`](../docs/desktop/local_control_sidecar_protocol_v1.md). Not Playwright inside desktop; **`/api/browser`** remains on FastAPI.
- **Download and run:** builds read **`default-public-api.json`** next to `main.cjs` with the **project’s public Ham API origin**. If `HAM_DESKTOP_API_BASE` / `ham-desktop-config.json` are unset, desktop uses this default (packaged and dev). Bump that file when the canonical public API URL changes, then cut a new desktop release.
- **Menu bar:** on **Linux and Windows**, the default Electron **File / Edit / View** menu is **removed** so the window chrome stays dark; **macOS** keeps the normal app menu.
- **Public assets:** the nav logo uses the same **relative `public/` URLs** as the Vite build (`base: ./`) so icons load under **`file://`** in the packaged renderer.

### Web vs packaged chat UI (single source)

Linux and Windows artifacts **do not duplicate** the chat interface. `electron-builder` copies **`../frontend/dist`** into `resources/renderer/` (`desktop/package.json` → `extraResources`). Any change under **`frontend/src`** (including `/chat`) applies to desktop automatically **after** you rebuild the web app and repackage:

- **Dev:** `npm start` from `desktop/` loads the Vite dev server by default, so you see the same React app as the browser.
- **Release:** run **`npm run pack:win`** (runs `build:frontend` first). Bump `version` in `desktop/package.json` when shipping so users can tell builds apart. Legacy **Linux AppImage / `.deb`** pipelines were removed; Windows Electron packaging (`pack:win*`) remains. Develop on Linux with **`npm start`** in `desktop/` (no installer).

### Download manifest · update prompts

- Canonical download metadata (`channel`, SHA-256 fingerprints, artifact URLs aligned with GitHub Releases) ships as **`frontend/public/desktop-downloads.json`**. Keep the embedded **`frontend/src/lib/ham/desktop-downloads.manifest.json`** copy in sync so the landing page has a deterministic first paint and TypeScript can compile against the same blob.
- On startup, **`desktop/desktop_updates.cjs`** compares **packaged** `app.getVersion()` against the **matching OS entry** (`linux`/`windows`; mac unsupported for now). If the manifest lists a **newer semver**, the user gets **Update** / **Later** — **Update** opens the **`release_page_url`** (fallback: direct `url`) in the browser. There is **no** built-in updater or silent reinstall.
- Trusted fetch defaults to `https://raw.githubusercontent.com/Code-Munkiz/ham/main/frontend/public/desktop-downloads.json`. Override via **`HAM_DESKTOP_DOWNLOADS_MANIFEST_URL`** if you maintain a fork; non-HTTPS / non-allowlisted URLs are refused. **`HAM_DESKTOP_UPDATE_CHECK=0`** skips the prompt; **`HAM_DESKTOP_UPDATE_CHECK=1`** forces checks even during **unpackaged** desktop dev (otherwise dev skips to avoid noisy dialogs).

### CI note

- **[`/.github/workflows/ci.yml`](../.github/workflows/ci.yml)** runs **pytest + frontend `tsc`** — it never packages Electron desktops.
- **Tagged Windows desktops:** **[`/.github/workflows/desktop-release.yml`](../.github/workflows/desktop-release.yml)** builds `pack:win` on **`desktop-v*`** pushes, uploads **`*.exe` + `.sha256`**, writes a **[GitHub Release](https://docs.github.com/repositories/releasing-projects-on-github/managing-releases-in-a-repository)**, and prints a manifest snippet into the workflow summary. **`workflow_dispatch`** runs the pack + checksum steps and uploads **`dist-pack/**` artifacts only (**no Release**).
- Maintainer step: manually sync **`frontend/public/desktop-downloads.json`** (and **`frontend/src/lib/ham/desktop-downloads.manifest.json`**) plus deploy the web bundle — drift prevention is spelled out in **[`docs/desktop/RELEASE_PIPELINE.md`](../docs/desktop/RELEASE_PIPELINE.md)**.

## HAM + Hermes curated bundle (desktop)

- **Terminology:** for how **desktop-side** (this app) and **API-side** (Ham API / broker) checks differ, see [docs/TEAM_HERMES_STATUS.md](../docs/TEAM_HERMES_STATUS.md).
- Shipped under `desktop/curated/`: README, `default-curated-skills.json` (suggested `catalog_id` pins), and `ham-api-env.snippet`. These are included in the packaged app (`package.json` → `files`).
- **Settings → HAM + Hermes setup** (desktop only): probes `hermes --version` on the **system PATH** and shows the curated list. HAM does **not** download or install Hermes binaries in this phase; install upstream, then use **Re-check CLI**.
- **Allowlisted CLI presets (Phase B):** buttons that run a **fixed** argv list in the main process (`hermes --version`, `hermes plugins list`, `hermes mcp list`, …) and show stdout/stderr in the settings panel — not free-form TUI control; 25s timeout, capped output. Presets are defined in `main.cjs` only; add new ones there after review.
- Additional IPC: `window.__HAM_DESKTOP_BUNDLE__` and **`window.hamDesktop`** share the same `localControl` bridge (status, policy, audit, kill switch, sidecar — **no browser session IPC**) — see `preload.cjs`, `main.cjs`, `local_control_*.cjs`.
- **CLI (repo, no Electron):** `ham desktop local-control status|policy|audit|browser|sidecar` (`browser` reflects **not_shipped** for Electron-managed sessions). Sidecar lifecycle stubs: `sidecar health|stop|start` = **electron_only**.
- **Tests:** `npm run test:local-control` from `desktop/` (Node built-in test runner: `local_control_*.test.cjs`, `preload_contract.test.cjs`, `desktop_updates.test.cjs`).

## Security (M1)

- Main: window lifecycle, reads optional `userData/ham-desktop-config.json`, merges env.
- Preload: `contextBridge.exposeInMainWorld('__HAM_DESKTOP_CONFIG__', …)` and `__HAM_DESKTOP_BUNDLE__` — no Node in the renderer (`nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`).
- Phase 2+ ([`docs/desktop/local_control_v1.md`](../docs/desktop/local_control_v1.md)) extends this seam — do not add filesystem/process IPC without review.

## Runtime API base

Resolve order in the renderer ([`getApiBase()`](../frontend/src/lib/ham/api.ts)):

1. Non-empty `window.__HAM_DESKTOP_CONFIG__.apiBase` (injected before the app runs).
2. Build-time `VITE_HAM_API_BASE` (web / static builds).
3. Dev: `""` → same-origin `/api/*` (Vite proxy).

Shell-side sources (merged in main, passed to preload via sync IPC):

- `HAM_DESKTOP_API_BASE` — non-empty forces absolute API origin (local, staging, or prod).
- `userData/ham-desktop-config.json` — optional `{"apiBase":"https://…"}` (see Electron `app.getPath('userData')` on your OS).
- `desktop/default-public-api.json` — default fallback when env/file are unset (packaged + dev).
- Env wins over file for `apiBase`.

## Linux dev workflow (recommended)

Terminal 1 — API:

```bash
cd /path/to/ham
.venv/bin/python scripts/run_local_api.py
```

(Or classic: `PYTHONPATH=. uvicorn src.api.server:app --reload --host 127.0.0.1 --port 8000`.)

Terminal 2 — Vite (proxy `/api` → 8000 by default):

```bash
cd frontend
BROWSER=none npm run dev
```

Terminal 3 — Electron (loads `http://127.0.0.1:3000`, uses `default-public-api.json` unless you set `HAM_DESKTOP_API_BASE`):

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

## Linux desktop installers removed

HAM no longer publishes **`npm run pack:linux`** targets (AppImage / `.deb`) from this repo. Packaging for **Windows** remains (**`npm run pack:win*`**). On Linux/macOS use **`cd desktop && npm start`** during development — that does **not** produce installers.

---

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

## Windows packaging (x64, from Linux)

electron-builder can produce **Windows x64** artifacts on a Linux host. This repo defaults to a **portable** `.exe` so you get a **single file** suitable for internal testing. A classic **NSIS installer** (graphical setup `.exe`) is optional via **`pack:win:nsis`** but **requires Wine on Linux** (or build on Windows).

### Why portable first, NSIS setup second?

On Linux, **`npm run pack:win`** (portable) has been verified **without** installing system Wine. **`npm run pack:win:nsis`** fails with *`wine is required`* until Wine is available (see [electron-builder multi-platform](https://www.electron.build/multi-platform-build#linux)). Use portable for Linux CI and quick handoff; add Wine or build on Windows when you need the Setup wizard.

### Cross-build note: `signAndEditExecutable: false`

Windows builds set **`signAndEditExecutable: false`** so Linux hosts do not need Wine for **rcedit** / integrity patching on the main executable. Trade-off: metadata/icon embedding on the `.exe` may be minimal compared to a signed Windows-native build. This matches **unsigned internal/test** builds.

### Prerequisites

- Node **20–24**, `frontend` dependencies installed (`cd ../frontend && npm install`).

### Build commands

From `desktop/`:

| Command | Output | Wine on Linux? |
|---------|--------|----------------|
| `npm run pack:win` | `dist-pack/HAM-Desktop-<version>-Win-x64-Portable.exe` | No |
| `npm run pack:win:dir` | `dist-pack/win-unpacked/` (run `HAM Desktop.exe` inside) | No |
| `npm run pack:win:nsis` | `dist-pack/HAM-Desktop-<version>-Win-x64-Setup.exe` | **Yes** (or use Windows) |

Example (portable, recommended for first internal testing):

```bash
cd desktop
npm install
npm run pack:win
```

### Test on a Windows machine

Copy the portable `.exe` or zip **`win-unpacked/`** to Windows. First run may trigger **Microsoft Defender SmartScreen** (“Unknown publisher”) because the build is **not code-signed** — use “More info” → “Run anyway” for internal testing only.

**API base** and **`file://` / `Origin: null` / `HAM_CORS_ORIGINS`** behave as documented in the packaged CORS section above. Set `HAM_DESKTOP_API_BASE` or `userData`-local `ham-desktop-config.json` so the dashboard can reach your Ham API.

### CI / clean builds

- Reuse `desktop/dist-pack/` hygiene between releases (`gitignored` scratch output).

## Environment reference

| Variable | Purpose |
|----------|---------|
| `HAM_DESKTOP_DEV_SERVER_URL` | URL to load in `devserver` mode (default `http://127.0.0.1:3000`) |
| `HAM_DESKTOP_LOAD_MODE` | `devserver` (default) or `file` |
| `HAM_DESKTOP_WEB_ROOT` | Directory containing `index.html` for `file` mode (default `../frontend/dist`) |
| `HAM_DESKTOP_API_BASE` | Ham API origin for runtime `getApiBase()` |
| `HAM_DESKTOP_USE_HASH_ROUTER` | `1` / `true` to force HashRouter (usually auto for `file` mode) |

## Windows local-control smoke (dev)

PowerShell terminals from repo root (`C:\Projects\GoHam\ham`):

### 1) Start frontend renderer (required in devserver mode)

```powershell
cd frontend
npm install
npm run dev
```

Expected renderer URL: `http://127.0.0.1:3000` (matches `frontend/package.json` and desktop default `HAM_DESKTOP_DEV_SERVER_URL`).

### 2) Start HAM Desktop with local bridge enabled

```powershell
cd desktop
npm install
$env:HAM_LOCAL_WEB_BRIDGE_ENABLED="true"
$env:HAM_LOCAL_WEB_BRIDGE_PORT="8765"
npm start
```

### 3) Verify bridge health + localhost-only bind

```powershell
curl.exe -i -H "Origin: https://ham-nine-mu.vercel.app" "http://127.0.0.1:8765/ham/local-control/v1/health"
netstat -ano | findstr :8765
```

Expected:
- Health returns `200` with `ok: true`.
- Listener shows `127.0.0.1:8765`.
- No `0.0.0.0:8765` listener.

### 4) Pairing flow

1. In HAM Desktop: `Settings -> Agent behavior -> Local Control / Pairing`, click **Generate pairing code**.
2. In web app (or plain-web pairing panel), paste code into **Pairing code** and click **Pair**.
3. Confirm **Status read** becomes available (authenticated `/status` succeeds).

### 5) Browser handoff + policy checks

1. Run browser handoff to `https://example.com`.
2. Confirm Chrome/Edge launches with managed HAM profile and screenshot/status is returned.
3. Run blocked URL check with `http://localhost:3000` and confirm policy block (no bypass).

### 6) Escalation skeleton check

From pairing panel, request escalation with trigger `partial` + explicit confirmation.

Expected:
- status `approved_pending_execution`
- `machine_execution_available: false`
- no machine action execution
