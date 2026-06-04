# Native Hermes workspace execution on Cloud Run

Native Hermes builds use **filesystem-oriented** `hermes chat` in an isolated workspace directory — not `complete_artifact_turn`, not JSON file bundles, not legacy chat scaffold.

**Image:** the `ham-api` Dockerfile installs **`hermes-agent`** from PyPI (pinned `HERMES_AGENT_VERSION`) and exposes **`/usr/local/bin/hermes`** on `PATH`.

**Staging gate:** do **not** set `HAM_HERMES_NATIVE_WORKSPACE_ENABLED=1` until provider auth is confirmed on the **native-build worker** host. Enabling the flag without a working CLI + auth yields `HERMES_CLI_UNAVAILABLE` or failed builds — there is no fallback to JSON artifact mode.

## Architecture

| Role | Service | Hermes CLI required? |
|------|---------|----------------------|
| Chat enqueue | `ham-api` | No (only `HAM_HERMES_NATIVE_WORKSPACE_ENABLED` for preflight) |
| Build execution | Worker URL (`HAM_NATIVE_BUILD_WORKER_URL`, often same Cloud Run service) | **Yes** |

Flow: `start_native_build_job` → Cloud Tasks → `POST /api/internal/native-build/execute` → `execute_native_build_job` → `hermes chat -q … -Q --yolo` with `cwd` = isolated workspace → `materialize_files_to_snapshot`.

## Docker / image verification

After building the image locally:

```bash
docker build -t ham-hermes-workspace-smoke .
./scripts/verify_hermes_cli_image.sh ham-hermes-workspace-smoke
```

Smoke checks:

- `command -v hermes`
- `hermes --version`
- `python -c "from src.ham.hermes_runtime_inventory import resolve_hermes_cli_binary; …"`

## Worker env (enable only after auth smoke)

Set on **both** `ham-api` (preflight) and the **native-build worker** (execution):

| Variable | Required | Notes |
|----------|----------|-------|
| `HAM_HERMES_NATIVE_WORKSPACE_ENABLED` | **Yes** to turn lane on | `1` / `true` / `yes` / `on` |
| `HAM_HERMES_CLI_PATH` | No if `hermes` on `PATH` | Override only for non-default binary location |
| `HERMES_NATIVE_WORKSPACE_MAX_TURNS` | No | Default `40`; CLI `--max-turns` cap |
| `HERMES_NATIVE_WORKSPACE_TIMEOUT_SEC` | No | Default `600`; subprocess budget — **Cloud Run request timeout must exceed this** |
| `HERMES_NATIVE_WORKSPACE_PROVIDER` | **Recommended for OpenRouter** | Passed as `hermes chat --provider` (e.g. `openrouter`) |
| `HERMES_NATIVE_WORKSPACE_MODEL` | **Recommended for OpenRouter** | Passed as `hermes chat -m` (e.g. `anthropic/claude-3.5-haiku`; OpenRouter has no default model) |
| `HAM_HERMES_NATIVE_WORKSPACE_ROOT` | No | Default `~/.ham/native-workspaces/{ws}/{proj}/{job}` (ephemeral container disk) |

Durable builder stores (already required for multi-instance staging):

- `HAM_NATIVE_BUILD_CONTEXT_STORE_BACKEND=firestore`
- `HAM_BUILDER_SOURCE_STORE_BACKEND=firestore`
- `HAM_BUILDER_RUNTIME_STORE_BACKEND=firestore` (preview enqueue)
- Native dispatch: `HAM_NATIVE_BUILD_DISPATCH=cloud_tasks`, `HAM_NATIVE_BUILD_WORKER_URL`, Cloud Tasks + OIDC vars (see `.env.example`)

## Hermes CLI auth on Cloud Run

The workspace adapter runs `hermes chat` with `env=os.environ.copy()`. **`HERMES_GATEWAY_API_KEY` / HTTP gateway mode does not substitute for CLI auth.**

Supported operator patterns (pick one):

### A. Provider env vars (recommended for Cloud Run)

Mount existing Secret Manager bindings already used by Ham:

| Secret / env | Hermes use |
|--------------|------------|
| `ANTHROPIC_API_KEY` | `anthropic` provider (already in `scripts/deploy_ham_api_cloud_run.sh` `--set-secrets`) |
| `OPENROUTER_API_KEY` | OpenRouter provider when set |

Hermes reads standard provider env vars; no `~/.hermes` login required for headless `hermes chat -Q --yolo`.

**Staging OpenRouter smoke (2026-06):** `OPENROUTER_API_KEY` + `--provider openrouter -m anthropic/claude-3.5-haiku` returned `HAM_HERMES_CLI_SMOKE_OK`. Without `-m`, Hermes failed with `No models provided`. Set `HERMES_NATIVE_WORKSPACE_PROVIDER` and `HERMES_NATIVE_WORKSPACE_MODEL` on the worker before enabling workspace mode.

**Operator smoke** (on a built image, with keys injected, **not** in CI logs):

```bash
docker run --rm -e ANTHROPIC_API_KEY=… ham-hermes-workspace-smoke \
  sh -lc 'hermes chat -q "Reply OK only" -Q --max-turns 1 --provider anthropic --source ham_native_builder_smoke'
```

### B. Mounted Hermes home (optional)

Set `HERMES_HOME` or `HAM_HERMES_HOME` to a volume with `config.yaml` / `.env` from `hermes login` or operator setup. Ephemeral `HERMES_HOME=/root/.hermes` is created in the image but **empty** until configured.

### Unresolved without operator action

- Interactive `hermes login` / TUI setup inside Cloud Run
- Relying only on private GCE **HTTP** Hermes gateway (`HERMES_GATEWAY_BASE_URL`) — that path serves chat API, not subprocess workspace builds

## ham-api vs worker

| Host | `HAM_HERMES_NATIVE_WORKSPACE_ENABLED` | Hermes binary | Provider secrets |
|------|----------------------------------------|---------------|------------------|
| `ham-api` | Yes (to start jobs) | Optional | Optional |
| Native-build worker | Yes | **Required** | **Required** for real builds |

## Related docs

- `docs/DEPLOY_CLOUD_RUN.md` — deploy + HTTP Hermes gateway on GCE
- `docs/HERMES_UPSTREAM_CONTRACT_AUDIT.md` — CLI vs HTTP API surfaces
- `src/ham/hermes_workspace_execution.py` — provider module docstring
