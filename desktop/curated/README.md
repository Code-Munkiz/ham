# HAM Desktop + Hermes — curated default bundle

This folder ships **inside the HAM Desktop** package. It is **documentation and pin lists** only: the app does
not auto-install system packages without your action.

## What “bundle” means here

- **HAM** = this repo’s **FastAPI dashboard + Context Engine** (run locally or use a hosted API).
- **Hermes** = the **NousResearch Hermes Agent** runtime (CLI + optional HTTP gateway), installed on your machine
  like any other tool (`hermes` on your `PATH`).
- **Curated skills** = a **default list of `catalog_id`s** (see `default-curated-skills.json`) you can install
  through Hermes’ normal skills flow once the CLI is available.

HAM remains **in control of policy and audit**; Hermes remains **the operator’s runtime** on disk.

## Install Hermes (operator machine)

1. Follow the current install instructions for **Hermes Agent** from the upstream project (pipx, brew, or release
   tarball — pick what matches your OS).
2. Verify in a real terminal: `hermes --version`
3. Start the **Ham API** (see repo root `README` / `uvicorn src.api.server:app`) and point the desktop at it
   (`HAM_DESKTOP_API_BASE` or bundled `default-public-api.json` for hosted APIs).

**TTY note:** some `hermes tools --summary` output needs an interactive terminal. The HAM **Capabilities** page
is read-only over HTTP; use a terminal for full CLI menus.

## Curated skills list

The JSON file `default-curated-skills.json` lists **suggested** `catalog_id` values (cross-platform where possible).
Install via Hermes’ own mechanisms after install — HAM does not execute installs from this panel in Phase 1.

## API env snippet

See `ham-api-env.snippet` for example variables when running the Ham API next to a local or remote Hermes HTTP
gateway. Copy values into your repo root `.env` as needed; never commit secrets.
