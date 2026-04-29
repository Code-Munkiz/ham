# HAM model recovery runbook

Restore HAM dashboard chat when it becomes unresponsive after LLM or model configuration changes.

**Related:** [`docs/HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md) (adapter modes and streaming), [`docs/DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) (Cloud Run env, private Hermes on GCE).

---

## Key principle

HAM chat depends on **two layers** that must stay aligned:

1. **Cloud Run (`ham-api`)** — set at least:
   - `HERMES_GATEWAY_MODEL`
   - `HAM_CHAT_FALLBACK_MODEL` (HTTP retry path; see API model catalog / hub)
   - `HERMES_GATEWAY_MODE=http` when using a private Hermes-compatible gateway
   - `HERMES_GATEWAY_BASE_URL` — internal URL to the VM (no `/v1` suffix)

2. **Hermes VM** — `~/.hermes/config.yaml` (path may vary by install user):
   - `model.default`
   - `fallback_providers`

Changing **only** Cloud Run or **only** Hermes can produce “ready” hub status while chat still fails (blank stream, hang, or empty assistant bubble).

---

## When to use this runbook

- Chat shows a **blank assistant** bubble or **never completes** / hangs.
- `GET /api/hermes-hub` looks healthy but **chat still fails**.
- A model was recently changed (provider swap, MiniMax, Qwen, etc.).

---

## Reference topology (substitute your org’s values)

The values below are a **concrete example** for a private Hermes VM behind Cloud Run; replace VM name, zone, IPs, and Linux user with yours.

| Item | Example |
|------|---------|
| VM name | `hermes-api-vm` |
| Zone | `us-west1-a` |
| Internal IP | `10.138.0.2` (RFC1918; use the value that Cloud Run’s VPC path can reach) |
| OS user owning Hermes | `user` |
| Hermes config | `/home/user/.hermes/config.yaml` |
| Gateway health (on the VM) | `http://127.0.0.1:8642/health` |

Do **not** rely on a public IP for production Hermes; prefer internal IP + VPC egress from Cloud Run (see [`docs/DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) “Private Hermes on GCE”).

---

## Recovery steps

### 1. Check Cloud Run (`ham-api`)

Confirm the **deployed** revision has at least:

```txt
HERMES_GATEWAY_MODE=http
HERMES_GATEWAY_BASE_URL=http://<VM_INTERNAL_IP>:8642
HERMES_GATEWAY_MODEL=<slug Hermes will accept>
HAM_CHAT_FALLBACK_MODEL=<fallback slug>
HERMES_GATEWAY_API_KEY=<secret; Secret Manager recommended>
```

Inspect with your org’s process, for example:

```bash
gcloud run services describe ham-api --region=us-central1 --format='yaml(spec.template.spec.containers[0].env)'
```

(Adjust **region** / **service** if yours differ; staging defaults in this repo often use `us-central1` — see [`docs/DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md).)

### 2. SSH into the Hermes VM

Use `gcloud compute ssh` or your standard bastion workflow, for example:

```bash
gcloud compute ssh user@hermes-api-vm --zone=us-west1-a
```

### 3. Backup config

```bash
cp /home/user/.hermes/config.yaml \
   /home/user/.hermes/config.yaml.bak."$(date +%Y%m%d-%H%M%S)"
```

### 4. Inspect config

```bash
sed -n '1,200p' /home/user/.hermes/config.yaml
```

Verify **`model.default`** and **`fallback_providers`** match what Cloud Run sends (`HERMES_GATEWAY_MODEL` / `HAM_CHAT_FALLBACK_MODEL`) in intent: same provider family and slugs Hermes can route.

### 5. Safe recovery baseline (example)

Align Hermes with a known-good OpenRouter slug (validate the exact string in OpenRouter if this revision stops working):

```yaml
model:
  default: qwen/qwen3.5-flash-02-23

fallback_providers:
  - provider: openrouter
    model: qwen/qwen3.5-flash-02-23
```

Edit the file with `sudo -u user` if root owns the tree but Hermes runs as `user`.

### 6. Restart Hermes gateway

```bash
sudo -u user /home/user/.local/bin/hermes gateway restart
```

If restart fails:

```bash
sudo -u user /home/user/.local/bin/hermes gateway stop
sudo -u user /home/user/.local/bin/hermes gateway start
```

(Adjust path to `hermes` if installed elsewhere, e.g. another venv or `PATH`.)

### 7. Verify Hermes (on the VM)

```bash
curl -sS http://127.0.0.1:8642/health
```

Expected includes JSON like: `{"status":"ok"}` (exact fields depend on Hermes build).

### 8. Verify HAM API

From a machine that can reach the API (with auth if your deployment requires it):

```bash
curl -sS "${HAM_API_BASE}/api/hermes-hub"
```

Check:

- `gateway_mode` is **`http`** when using the private gateway.
- `http_chat_ready` is **`true`** (and `dashboard_chat_ready` if you rely on it in the UI).

### 9. Verify web chat

Send a short message in the dashboard. Expect a normal streamed reply — no permanent blank assistant bubble.

---

## Rollback

List backups (newest first):

```bash
ls -lt /home/user/.hermes/config.yaml.bak.*
```

Restore a specific file (replace the placeholder with the real backup filename):

```bash
sudo -u user cp /home/user/.hermes/config.yaml.bak.YYYYMMDD-HHMMSS \
   /home/user/.hermes/config.yaml
sudo -u user /home/user/.local/bin/hermes gateway restart
```

---

## Critical warnings

- Do **not** assume fixing **only** Cloud Run env fixes Hermes (or the reverse).
- Do **not** deploy **MiniMax** (or similar) as the sole path without **fallback + timeout** hardening verified under load.
- Do **not** leave **`model.default`** on Hermes inconsistent with **`HERMES_GATEWAY_MODEL`** / **`HAM_CHAT_FALLBACK_MODEL`** on Cloud Run without understanding how Hermes resolves overrides.

---

## Model notes

- **Baseline example:** primary `qwen/qwen3.5-flash-02-23`, fallback the same, is a conservative recovery pair; re-validate slugs periodically against OpenRouter / Hermes docs.
- **MiniMax:** re-enable only after fallback routing and client timeouts are proven in staging.

---

## Escalation

If Hermes fails to start or chat still fails after alignment:

1. Inspect system / process logs (`journalctl`, Hermes logs per your install).
2. Confirm **TCP** listener on **8642** (or your configured port) on the VM.
3. Confirm **VPC connectivity** from Cloud Run to the VM internal IP (firewall, connector, egress mode).

Then escalate per your org (on-call, ops channel, vendor).
