# HAM Browser Runtime (Playwright) v1

This doc covers local setup and runtime caveats for the HAM-owned Browser Runtime backend.

## v1 locked runtime decisions

- Runtime host: `ham_api_local`
- Screenshot transport: `binary_png_endpoint`
- Session ownership: `pane_owner_key`
- Domain policy: private/local targets blocked by default
- Not in v1: live streaming, Cursor browser embedding

## Install and local setup

1) Install Python dependencies:

```bash
pip install -r requirements.txt
```

2) Install Chromium for Playwright:

```bash
playwright install chromium
```

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
- `POST /api/browser/sessions/{session_id}/actions/type`
- `POST /api/browser/sessions/{session_id}/screenshot`
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

- No continuous remote-desktop/live stream transport.
- Selector-based action APIs only (no advanced DOM extraction contract yet).
- Session ownership is per pane owner key; no multi-user auth architecture in this pass.
