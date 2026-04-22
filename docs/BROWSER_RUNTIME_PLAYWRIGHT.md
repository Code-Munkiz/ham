# HAM Browser Runtime (Playwright) v1

This doc covers local setup and runtime caveats for the HAM-owned Browser Runtime backend.

## v1 locked runtime decisions

- Runtime host: `ham_api_local`
- Screenshot transport: `binary_png_endpoint`
- Session ownership: `pane_owner_key`
- Domain policy: private/local targets blocked by default
- Primary in-pane transport: HAM live `screenshot_loop` (poll + direct input forwarding)
- Not in v1: WebRTC media transport, Cursor browser embedding

## Install and local setup

1) Install Python dependencies:

```bash
pip install -r requirements.txt
```

2) Install Chromium for Playwright (not installed by `pip` alone):

```bash
playwright install chromium
```

Or from the repo root: `./scripts/install_playwright_chromium.sh` — it uses your **active venv**, or **`./.venv`**, or **creates `./.venv`** (needed on **PEP 668** systems like Ubuntu/Pop!_OS where system-wide `pip install` is blocked).

**Linux:** if Chromium still fails to launch (missing system libs), run `playwright install-deps chromium` in the same environment.

**Docker / Cloud Run:** the root `Dockerfile` runs `python -m playwright install --with-deps chromium` so images include the browser; bump memory if the container OOMs (Chromium is not free).

3) Start HAM API as usual (local dev):

```bash
uvicorn src.api.server:app --reload --port 8000
```

## Browser Runtime endpoints

- `GET /api/browser/policy`
- `POST /api/browser/sessions`
- `GET /api/browser/sessions/{session_id}?owner_key=...`
- `POST /api/browser/sessions/{session_id}/navigate`
- `POST /api/browser/sessions/{session_id}/actions/click`
- `POST /api/browser/sessions/{session_id}/actions/click-xy`
- `POST /api/browser/sessions/{session_id}/actions/scroll`
- `POST /api/browser/sessions/{session_id}/actions/key`
- `POST /api/browser/sessions/{session_id}/actions/type`
- `POST /api/browser/sessions/{session_id}/screenshot`
- `POST /api/browser/sessions/{session_id}/stream/start`
- `GET /api/browser/sessions/{session_id}/stream/state?owner_key=...`
- `POST /api/browser/sessions/{session_id}/stream/offer`
- `POST /api/browser/sessions/{session_id}/stream/candidate`
- `POST /api/browser/sessions/{session_id}/stream/stop`
- `POST /api/browser/sessions/{session_id}/reset`
- `DELETE /api/browser/sessions/{session_id}?owner_key=...`

## Policy and env defaults

Default behavior:

- Allow `http://` and `https://` schemes only.
- Block `localhost`, loopback, private/link-local/reserved/multicast IP targets.
- Block rate spikes and enforce session TTL.
- Return screenshot as `image/png` bytes.

Optional env controls:

- `HAM_BROWSER_ALLOW_PRIVATE_NETWORK` (`true|false`, default: `false`)
- `HAM_BROWSER_ALLOWED_DOMAINS` (comma-separated allowlist, optional)
- `HAM_BROWSER_BLOCKED_DOMAINS` (comma-separated denylist, optional)
- `HAM_BROWSER_SESSION_TTL_SECONDS` (default `900`)
- `HAM_BROWSER_MAX_ACTIONS_PER_MINUTE` (default `120`)
- `HAM_BROWSER_MAX_SCREENSHOT_BYTES` (default `5000000`)

## Host/runtime caveats

- Browser Runtime requires Playwright + Chromium installed on the API host.
- Some hardened/container hosts may require extra Chromium runtime libs.
- If Chromium sandbox constraints exist in a given host, launch config adjustments may be required in deployment-specific environments.

## Known v1 limitations

- This mode is a screenshot-loop live pane, not media-streaming remote desktop.
- Click accuracy depends on viewport/image alignment (`object-contain` mapping in pane code).
- Input path is single-controller (`pane_owner_key`), no collaborative co-control.
- WebRTC signaling routes exist for contract continuity but are not active transport in this pass.
- Selector/DOM extraction remains limited (no advanced extraction contract yet).
- Session ownership is per pane owner key; no multi-user auth architecture in this pass.
