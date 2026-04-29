# Team status: Hermes + HAM operator story

Operator-facing work that clarifies what **the Ham API** can observe versus what **this user’s machine** (HAM Desktop) can run locally, without claiming full Hermes TUI control or arbitrary shell from the browser.

## Current status summary

- **Command Center** (`/command-center`) is the **API-side, read-only** view of the Hermes + HAM “operator surface”: broker snapshot, allowlisted CLI snippets, `HERMES_GATEWAY_*` HTTP probe, model catalog, and honest stubs.
- **Settings → HAM + Hermes setup** (HAM **Desktop** only) is **desktop-side**: local `hermes` presence check, optional **allowlisted preset runs** (fixed argv in Electron main), and curated default pins. It is **not** a generic command runner and **not** a replacement for a terminal.
- **`operator_connection`** in `GET /api/hermes-gateway/snapshot` is a **single derived block** (CLI probe line, HTTP gateway probe state, HAM **chat** `gateway_mode`, snapshot freshness) so dashboards can show one coherent story. See [HERMES_GATEWAY_BROKER.md](HERMES_GATEWAY_BROKER.md).
- **Phase C (PTY / full Hermes TUI control)** is **roadmap / design only** after product and security sign-off — **not** implemented in app or API.

**One-liner for leadership:**  
*We shipped a safer Hermes operator layer: HAM now shows one unified connection view across CLI, API chat gateway, and desktop probes, and the desktop can run a few allowlisted Hermes checks — without pretending to control the full Hermes TUI or changing Hermes’ architecture.*

## What shipped (recent)

- Hermes **Gateway** / **Command Center** page with model/provider surfacing and **API-side** explanations (e.g. `http` mode: **config-controlled** upstream model, not a browser model switcher).
- **IA / navigation** cleanup (e.g. Command Center placement, Skills catalog entry, overview → activity redirect, settings return target).
- **`operator_connection`** on `/api/hermes-gateway/snapshot`.
- **Desktop** Settings: **HAM + Hermes setup** (curated files, local probe, API snapshot strip when reachable).
- **Allowlisted desktop preset checks:** `hermes --version`, `hermes plugins list`, `hermes mcp list` (fixed in `desktop/main.cjs` — not user-defined argv).
- **Desktop** app version in repo (e.g. **0.1.6** at time of this doc) — no release process documented here.

## What `operator_connection` means

A **convenience projection** in the JSON snapshot, built only from data the broker already had:

- **CLI probe** — result of the allowlisted `hermes --version` (or equivalent) on the **host running the Ham API** (not the end-user’s browser).
- **HTTP gateway** — probe to `HERMES_GATEWAY_BASE_URL` (e.g. `/health`), as configured on the **API** host.
- **`ham_chat_gateway_mode`** — from Hermes hub / chat routing (`HERMES_GATEWAY_MODE`): `openrouter` | `http` | `mock` | etc.
- **Snapshot meta** — `captured_at`, TTL, whether any **degraded** capability flags are set.

It does **not** add new `hermes` subcommands to the allowlist; see broker security notes.

## Differences (do not conflate)

| Concept | What it is |
|--------|------------|
| **Hermes CLI / operator machine** | The `hermes` binary and config on a given host (PATH or `HAM_HERMES_CLI_PATH` on the **API** host for broker probes; same idea on the **laptop** for Desktop’s **desktop-side** checks). TTY/curses **menus** are for a **real terminal**, not a REST API in v0.8.x. |
| **HAM API / HTTP gateway** | Server config (`HERMES_GATEWAY_BASE_URL`, `HERMES_GATEWAY_MODE`, API keys) defines how **`/api/chat`** talks to an upstream. **Read-only** snapshot probes (e.g. `/health`, optional `/v1/models` count hint) are **not** a live TUI. |
| **HAM Desktop local probe** | **Electron** runs `hermes` on **this** machine to verify install/version — **independent** of whether the **API** host has `hermes` installed. |
| **Read-only broker snapshot** | `GET /api/hermes-gateway/snapshot` — merged, **redacted** view for the dashboard. Cached with TTL; use **Refresh** or `refresh=true` to force recompute. |
| **Desktop preset checks** | **Allowlisted** argv only, executed in the **main process**, for **verification** — not “run any hermes subcommand” and not a **PTY**. |
| **Future PTY / capability host** | Hypothetical **local** host that could run interactive sessions under strict policy — **not** shipped; design-only until approved. |

## What HAM can do today

- Show a **unified, honest** **API-side** status (Command Center + `operator_connection` when present).
- **Read-only** discovery (Capabilities shop, skills catalog, inventory where API allows).
- **My library (Capability library):** the Ham API can **persist project-scoped bookmark-style refs** to the Hermes skills catalog and the first-party capability directory (`/api/capability-library/*`, on-disk under the project&rsquo;s `.ham/`, with a separate write token). This is **saving references only** — it does **not** install to Hermes or run shell from the browser; **installed** and **active** state still come from real inventory and Hermes config (see [AGENTS.md](../AGENTS.md) and `docs/capabilities/`).
- **Desktop**: **verify** local `hermes` and run **fixed** preset **checks** with capped output and timeout.
- Route **chat** per **`HERMES_GATEWAY_MODE`** (OpenRouter vs HTTP upstream vs mock) **server-side** — browser never holds provider secrets for gateway.

## What HAM cannot do today

- **Drive** the full Hermes **TUI** or every **menu** item from the web app.
- **Arbitrary** `hermes` argv from the **browser** (no browser-to-shell, no generic runner).
- **Switch** the upstream Hermes **HTTP** “runtime model” from the HAM **UI** when mode is `http` — that remains **config-controlled** on the API/upstream.
- **Guarantee** that **local** desktop Hermes state matches **server** broker CLI state (different machines).

## Safe boundaries (non-negotiable)

- **No** arbitrary browser-to-shell: renderer does not get open `hermes` argv.
- **No** full **TUI** control from HAM (Hermes v0.8.x has no official REST for that; TTY stays TTY).
- **No** generic **Hermes command runner** in the product UI — only **allowlisted** desktop presets in **main**.
- **No** **secrets** in the frontend: keys stay env/server; snapshots **omit** redacted CLI blobs in public JSON.
- **No** new **orchestration framework** (Hermes-supervised, single-control-plane contract unchanged).

## How to sanity-check

| Check | What to do |
|-------|------------|
| **Command Center** | Open `/command-center`, read header and **operator connection** strip. Confirm you understand “API host” vs “this laptop”. |
| **Settings → HAM + Hermes** | **Desktop** only. Local probe + **allowlisted** buttons + (if API up) **API** strip. |
| **`/api/hermes-gateway/snapshot`** | `GET` from a client that can reach the API; verify `operator_connection` and `degraded_capabilities`. |
| **Desktop preset buttons** | Run a preset; expect **only** the fixed commands in `main.cjs`, stdout/stderr in panel. |

## Troubleshooting matrix

| Symptom | Likely meaning | Where to check | What not to assume |
|--------|----------------|---------------|----------------------|
| **CLI green, chat still fails** | **Chat** path uses **OpenRouter** or **HTTP** mode with **separate** keys/URL; CLI only proves `hermes` on **API** host. | `HERMES_GATEWAY_MODE`, `HERMES_GATEWAY_BASE_URL`, API logs, `/api/chat` errors. | That **CLI** fixes **LLM** routing. |
| **HTTP gateway probe green, desktop Hermes probe fails** | **API** can reach `HERMES_GATEWAY_BASE_URL`; **this laptop** may lack `hermes` on **PATH**. | Desktop **Settings** local probe; `HAM_HERMES_CLI_PATH`. | That **desktop** install fixes **server** **HTTP** probe. |
| **Desktop probe green, API snapshot says CLI unavailable** | **Two machines**: API host has no `hermes` in PATH, but your **Mac/PC** does (or vice versa). | Where **uvicorn** runs vs where **Electron** runs. | A single “green” covers both. |
| **`/v1/models` count present, no model selector in HAM** | In **`http` mode**, HAM may show a **count hint** only; **chat model** is **config-controlled**, not a browser pulldown for Hermes upstream. | Command Center “Effective model / gateway” copy. | That `/v1/models` implies **HAM** can switch **Hermes**’ upstream model. |
| **External runner “stub”** | Placeholder or not wired for your profile — by design in parts of the broker. | **External Runners** tab, broker placeholders. | That **stub** means production-ready. |
| **Settings API strip unavailable** | UI cannot reach `GET /api/.../snapshot` (wrong **API base**, CORS, API down, or not logged in as required). | `VITE_HAM_API` / `HAM_DESKTOP_API_BASE`, network tab. | That **local** `hermes` is broken. |
| **Command Center looks stale** | **TTL** cache; **Refresh** or `?refresh=true` on snapshot. | Refresh button, `freshness` in JSON. | That **data** is real-time for every sub-field without refresh. |
| **Activity** shows **demo** | API snapshot **unreachable** from browser. | `Activity` banner; API URL. | That **Activity** is a live system log. |

## Glossary

- **Operator connection** — In snapshot JSON, the **`operator_connection`** object: derived summary of CLI probe, HTTP probe, chat `gateway_mode`, and snapshot metadata.
- **CLI probe** — Allowlisted `hermes --version` (or equivalent) on the **Ham API** host, surfaced in the broker and **Command Center** (not the desktop **local** probe unless the same machine).
- **HTTP gateway** — The upstream URL HAM’s **server** may call for `http` chat mode, plus the broker’s read-only `GET {base}/health` (and optional count hints).
- **HAM chat gateway mode** — `HERMES_GATEWAY_MODE` / hub `gateway_mode`: how **`/api/chat`** routes the model (`openrouter` vs `http` vs `mock`, etc.).
- **Desktop probe** — **Electron** `hermes` check on **this** machine (`ham-desktop:hermes-cli-probe`); independent of the API **CLI** probe.
- **Broker snapshot** — `GET /api/hermes-gateway/snapshot`: read-only, redacted, possibly **cached** JSON.
- **Preset run** — **Allowlisted** fixed argv in **desktop** main; **not** user shell, not arbitrary.
- **TTY-required** — Some `hermes` subcommands need an interactive **terminal**; HAM’s HTTP/JSON **cannot** reproduce that; use a **shell**.
- **PTY / capability host** — Future idea: a **local** process hosting controlled PTY; **not** in production HAM; requires security review.
- **Stub adapter** — Placeholder row in the broker (e.g. “Path C” RPC) until upstream proves a real API.
- **Degraded capability** — String flags in the snapshot (e.g. `hermes_http_gateway`, `hermes_version_cli`) when a fragment failed or is misconfigured; **read** as advisory.

## Next roadmap (non-committing)

- **Copy** / **troubleshooting** polish in-app and in docs (this file, broker doc, `desktop/README.md`).
- **Richer** official Hermes health probes if/when a **stable** non-interactive contract exists and is **audited** (still **no** arbitrary argv from browser).
- **External runner** bridge replacements as products integrate (replaces **stub** rows when real).
- **Phase C** — PTY / **capability-host** **design** only, after product + **security** approval; no implementation in core until explicitly scheduled.

## Related docs

- [HERMES_GATEWAY_BROKER.md](HERMES_GATEWAY_BROKER.md) — broker contract and security.
- [HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md) — chat adapter contract (if present).
- [desktop/README.md](../desktop/README.md) — HAM Desktop load modes and Hermes **preset** security notes.
- [VISION.md](../VISION.md) — architecture table (operator snapshot + desktop **preset** language).
