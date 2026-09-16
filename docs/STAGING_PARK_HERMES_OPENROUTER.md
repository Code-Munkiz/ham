# Staging: park Hermes / OpenRouter (HAM idle)

**Purpose:** Stop **hosted HAM staging** from calling **OpenRouter** on the shared
`go_ham_v1+…` key **without** revoking the key (other products may use the same key).

**Parked on:** 2026-09-16 (operator decision — repo not actively in use).

**GCP project:** `clarity-staging-488201`

---

## What was burning OpenRouter

| Symptom on OpenRouter | Source |
|----------------------|--------|
| App **Hermes Agent**, model **qwen/qwen3.5-flash-02-23**, **`tool_calls`**, large prompt tokens | **Hermes agent loops** (tools + multi-turn), not Dependabot or GitHub CI |
| Bursts around top of hour | **`hermes-api-vm` gateway** long-running / scheduled agent work |

Architecture (normal staging):

```text
ham-api (Cloud Run)  ──http──►  hermes-api-vm:8642  ──►  OpenRouter (Hermes config)
ham-native-builder-worker      hermes chat --provider openrouter (when enabled)
```

Parking **Cloud Run alone** did not stop the VM gateway; that was the remaining **`tool_calls`** source after worker changes.

---

## Parked state (2026-09-16)

### Cloud Run `ham-api` (revision **ham-api-00374-7kq** and later)

| Variable | Parked value |
|----------|----------------|
| `HERMES_GATEWAY_MODE` | **`mock`** (no HTTP to private Hermes) |
| `HAM_HERMES_NATIVE_WORKSPACE_ENABLED` | **`0`** |
| `HAM_MEDIA_IMAGE_GENERATION_ENABLED` | **`0`** |
| `OPENROUTER_API_KEY` | **not mounted** on this service |

Other builder/GKE env may still be **enabled**; build **queues are paused** (below).

### Cloud Run `ham-native-builder-worker` (revision **ham-native-builder-worker-00021-hwx** and later)

| Variable / secret | Parked value |
|-------------------|----------------|
| `OPENROUTER_API_KEY` | **secret binding removed** (`ham-openrouter-api-key` stays in Secret Manager) |
| `HERMES_GATEWAY_MODE` | **`mock`** |
| `HAM_HERMES_NATIVE_WORKSPACE_ENABLED` | **`0`** |

### Cloud Tasks (location **us-central1**)

| Queue | State |
|-------|--------|
| `ham-native-builds` | **PAUSED** |
| `ham-builder-worker` | **PAUSED** |

### GCE **`hermes-api-vm`** (zone **us-west1-a**, private IP **10.138.0.2**)

| Item | Parked value |
|------|----------------|
| `hermes-gateway.service` (user systemd) | **`stop` + `disable`** (will not auto-start on boot) |

Journal at stop showed an active agent loop (iteration budget / tool calls) — matches OpenRouter **`tool_calls`** rows.

**Secret Manager:** keys (`ham-openrouter-api-key`, etc.) were **not** deleted.

---

## Verify parked (no new OpenRouter spend)

1. OpenRouter dashboard → filter key **`go_ham_v1+clarityASK`** → App **Hermes Agent** → confirm **no new** rows after park time.
2. GCP:

```bash
gcloud run services describe ham-api --project=clarity-staging-488201 --region=us-central1 \
  --format="value(spec.template.spec.containers[0].env)" | tr ';' '\n' | grep -E 'HERMES_GATEWAY_MODE|HAM_HERMES_NATIVE|OPENROUTER'

gcloud tasks queues list --project=clarity-staging-488201 --location=us-central1

gcloud compute ssh hermes-api-vm --project=clarity-staging-488201 --zone=us-west1-a --command \
  "sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active hermes-gateway || true"
```

Expect: `mock`, native `0`, no `OPENROUTER` on worker, queues **PAUSED**, gateway **inactive** or **failed** (not running).

3. **BYOK:** Signed-in users with OpenRouter in **Connected Tools** can still call OpenRouter from the browser even when platform env is mock — rare for long **`tool_calls`** chains; disable keys in UI if needed.

---

## Restore staging (when HAM should use Hermes / OpenRouter again)

**Order matters.** Re-enable gateway before turning native builds back on.

### 1. Hermes gateway VM

```bash
gcloud compute ssh hermes-api-vm --project=clarity-staging-488201 --zone=us-west1-a --command \
  "sudo -u user env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user enable --now hermes-gateway"
```

Confirm: `curl -sS -i http://10.138.0.2:8642/health` (from a host on the VPC — e.g. Cloud Run with egress, or SSH on VM).

Model / OpenRouter slugs: [`RUNBOOK_HAM_MODEL_RECOVERY.md`](RUNBOOK_HAM_MODEL_RECOVERY.md), [`HERMES_UPGRADE_RUNBOOK.md`](HERMES_UPGRADE_RUNBOOK.md).

### 2. Cloud Run `ham-api`

Use **`.gcloud/ham-api-env.yaml`** (gitignored) or explicit updates — do **not** commit secrets.

Typical restore:

- `HERMES_GATEWAY_MODE=http`
- `HERMES_GATEWAY_BASE_URL=http://10.138.0.2:8642` (no `/v1` suffix)
- `HERMES_GATEWAY_MODEL=hermes-agent` (or your validated slug)
- `HAM_HERMES_NATIVE_WORKSPACE_ENABLED=1` only when worker auth is verified

Deploy pattern: [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md), [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md).

### 3. Native builder worker

Re-mount OpenRouter only when native lane is ready:

```bash
gcloud run services update ham-native-builder-worker \
  --project=clarity-staging-488201 --region=us-central1 \
  --update-secrets=OPENROUTER_API_KEY=ham-openrouter-api-key:latest \
  --update-env-vars="HERMES_GATEWAY_MODE=http,HAM_HERMES_NATIVE_WORKSPACE_ENABLED=1,HERMES_NATIVE_WORKSPACE_PROVIDER=openrouter,HERMES_NATIVE_WORKSPACE_MODEL=anthropic/claude-3.5-haiku"
```

See [`NATIVE_HERMES_WORKSPACE_CLOUD_RUN.md`](NATIVE_HERMES_WORKSPACE_CLOUD_RUN.md).

### 4. Resume Cloud Tasks queues

```bash
gcloud tasks queues resume ham-native-builds --project=clarity-staging-488201 --location=us-central1
gcloud tasks queues resume ham-builder-worker --project=clarity-staging-488201 --location=us-central1
```

### 5. Smoke

- `scripts/verify_ham_api_deploy.sh` against staging URL (expect **non-mock** assistant text when `http` + healthy Hermes).
- One controlled builder turn; watch OpenRouter for expected volume.

---

## Related docs

| Doc | Role |
|-----|------|
| [HERMES_UPGRADE_RUNBOOK.md](HERMES_UPGRADE_RUNBOOK.md) | VM name, zone, systemd, config paths |
| [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) | Cloud Run env + secrets |
| [NATIVE_HERMES_WORKSPACE_CLOUD_RUN.md](NATIVE_HERMES_WORKSPACE_CLOUD_RUN.md) | Native worker + OpenRouter provider |
| [RUNBOOK_HAM_MODEL_RECOVERY.md](RUNBOOK_HAM_MODEL_RECOVERY.md) | qwen / OpenRouter slug recovery on Hermes |

---

## PowerShell note (Windows operators)

For `gcloud run services update --update-env-vars`, pass a **quoted** comma list so PowerShell does not merge keys into one value:

```powershell
gcloud run services update ham-api --project=clarity-staging-488201 --region=us-central1 `
  --update-env-vars="HERMES_GATEWAY_MODE=mock,HAM_HERMES_NATIVE_WORKSPACE_ENABLED=0"
```
