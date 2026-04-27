# Deploy Ham API to Google Cloud Run

This repo ships a **`Dockerfile`** that runs **`uvicorn src.api.server:app`**. The browser never talks to Cloud Run with vendor gateway paths; only Ham routes like **`POST /api/chat`**.

**End-to-end checklist (Vercel + GCP):** [`docs/DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md). After deploy, run **`scripts/verify_ham_api_deploy.sh`** with your API URL and the **exact** Vercel `Origin` you use in the browser.

## Source of truth: Clarity Staging (team GCP)

**Staging** Ham API deployments use this GCP project (console name **Clarity-Staging**):

| Setting | Value |
|--------|--------|
| **Project ID** | `clarity-staging-488201` |
| **Region** | `us-central1` |
| **Artifact Registry repo** | `ham` (Docker) |
| **Cloud Run service** | `ham-api` |

Use a **different** GCP project for production when your org splits prod/staging; this repo documents **staging** IDs only.

## What you do in GCP (not automatable from this repo)

1. Confirm you are in the right project: **`gcloud config set project clarity-staging-488201`** (or another project for a one-off).
2. Enable billing if required.
3. Enable APIs (Console or `gcloud`):
   - **Cloud Run Admin API**
   - **Artifact Registry API**
   - **Cloud Build API** (if you use `gcloud builds submit`)
   - **Secret Manager API** (for `CURSOR_API_KEY` and other secrets)
4. Create an **Artifact Registry** Docker repository (one-time), e.g. `ham`.
5. **Deploy** the image and set **environment variables** / secrets (see below).
6. Note the **service URL** (e.g. `https://ham-api-….run.app`) for **`VITE_HAM_API_BASE`** on Vercel.

IAM: start with **allow unauthenticated invoke** for a quick staging smoke test, or use **IAM** + **identity tokens** / API keys later.

## One-time: Artifact Registry

Defaults below match **Clarity Staging**. Substitute `PROJECT_ID` / `REGION` only for another environment.

```bash
gcloud config set project clarity-staging-488201
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories create ham \
  --repository-format=docker \
  --location=us-central1 \
  --description="Ham API images"
```

## Build and push the image

From the **repository root** (where this `Dockerfile` lives):

```bash
export PROJECT_ID=clarity-staging-488201
export REGION=us-central1
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/ham/ham-api:staging"

gcloud builds submit --tag "${IMAGE}" . --project="${PROJECT_ID}"
```

## Cursor Cloud API key (Secret Manager)

**Do not** put the Cursor API key in `ham-api-env.yaml` or other tracked files. On Cloud Run, inject **`CURSOR_API_KEY`** from Secret Manager. The app reads it from the environment (`get_effective_cursor_api_key`); the dashboard “save key” file is optional and is not durable on ephemeral containers without a volume.

1. **Create** the secret once, or **add a version** to rotate (use one or the other):

   ```bash
   export PROJECT_ID=clarity-staging-488201
   # First time only (fails if the secret id already exists):
   printf '%s' "$CURSOR_API_KEY" | gcloud secrets create ham-cursor-api-key --data-file=- --project="${PROJECT_ID}" --replication-policy=automatic
   # Rotate / update (when the secret already exists):
   printf '%s' "$CURSOR_API_KEY" | gcloud secrets versions add ham-cursor-api-key --data-file=- --project="${PROJECT_ID}"
   ```

2. **Grant** the Cloud Run runtime service account access (replace **`PROJECT_NUMBER`** with `gcloud projects describe clarity-staging-488201 --format='value(projectNumber)'`):

   ```bash
   gcloud secrets add-iam-policy-binding ham-cursor-api-key \
     --project=clarity-staging-488201 \
     --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   ```

   If the service uses a **custom** service account, bind that identity instead.

3. **Deploy** with **`--set-secrets=CURSOR_API_KEY=ham-cursor-api-key:latest`** (see below) in addition to **`--env-vars-file`**.

## Cloud Agent launch token (`HAM_CURSOR_AGENT_LAUNCH_TOKEN`)

Chat **`cursor_agent_launch`** requires a Ham **operator bearer** separate from **`CURSOR_API_KEY`**. On Cloud Run, store it in **Secret Manager** (not `.gcloud/ham-api-env.yaml`) so it is never committed.

1. **Create** the secret (skip if it already exists):

   ```bash
   export PROJECT_ID=clarity-staging-488201
   gcloud secrets create ham-cursor-agent-launch-token \
     --project="${PROJECT_ID}" \
     --replication-policy=automatic
   ```

2. **Add** a version without putting the token on the command line (pick one):

   ```bash
   # From an env var already set in your shell (not echoed):
   printf '%s' "$HAM_CURSOR_AGENT_LAUNCH_TOKEN" | gcloud secrets versions add ham-cursor-agent-launch-token \
     --project="${PROJECT_ID}" \
     --data-file=-
   ```

3. **Grant** the Cloud Run runtime service account **`roles/secretmanager.secretAccessor`** on **`ham-cursor-agent-launch-token`** (use the same member as for **`ham-cursor-api-key`** — see above).

4. **Deploy** with **`HAM_CURSOR_AGENT_LAUNCH_TOKEN=ham-cursor-agent-launch-token:latest`** in **`--set-secrets`** alongside Cursor and Hermes keys. The default in **`scripts/deploy_ham_api_cloud_run.sh`** includes this mapping.

5. **Browser:** paste the **same** secret value in the Cloud Agent launch field (or retrieve the current version locally with `gcloud secrets versions access latest --secret=ham-cursor-agent-launch-token --project="${PROJECT_ID}"`).

## Deploy to Cloud Run

```bash
export PROJECT_ID=clarity-staging-488201
export REGION=us-central1
export SERVICE=ham-api
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/ham/ham-api:staging"

# Prefer an env YAML file: commas in HAM_CORS_ORIGINS break `--set-env-vars` parsing.
# Copy `docs/examples/ham-api-cloud-run-env.yaml` to `.gcloud/ham-api-env.yaml` (gitignored) and edit.
#
# Important: each `gcloud run deploy --env-vars-file …` supplies the **full** set of plain env vars for
# the new revision. A file that sets `HERMES_GATEWAY_MODE: mock` (the doc example default) will force
# mock chat and **drop** any Hermes HTTP/OpenRouter vars that existed only on the previous revision.
# Before redeploying staging, diff against a known-good revision: `gcloud run revisions describe REV --format=yaml(spec.containers[0].env)`.

gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --project "${PROJECT_ID}" \
  --env-vars-file .gcloud/ham-api-env.yaml \
  --set-secrets=CURSOR_API_KEY=ham-cursor-api-key:latest,HERMES_GATEWAY_API_KEY=ham-hermes-gateway-api-key:latest,HAM_CURSOR_AGENT_LAUNCH_TOKEN=ham-cursor-agent-launch-token:latest
```

Add more env vars as needed, e.g. **`HERMES_GATEWAY_MODE=http`**, **`HERMES_GATEWAY_BASE_URL`**, **`HERMES_GATEWAY_API_KEY`**, **`OPENROUTER_API_KEY`** (use **Secret Manager** for secrets in real deployments).

### Hermes gateway key (`HERMES_GATEWAY_API_KEY` — fix “Gateway HTTP 401” in chat)

In **http** mode Ham sends **`Authorization: Bearer <key>`** to Hermes. If **`HERMES_GATEWAY_API_KEY`** is missing on Cloud Run, the upstream often returns **401** (and streaming chat may return **200** with an **NDJSON** `error` line, so do not rely on log filters for `httpRequest.status=401` only).

1. **Create the secret** (same token Hermes expects for Bearer auth) — one-time, from a machine with `gcloud` and project access:

   ```bash
   export PROJECT_ID=your-gcp-project
   # Pipe the raw key, or: ./scripts/seed_hermes_gateway_api_key.sh ./key.txt
   printf '%s' 'YOUR_HERMES_BEARER_TOKEN' | ./scripts/seed_hermes_gateway_api_key.sh
   ```

2. **Deploy** with the secret mounted as **`HERMES_GATEWAY_API_KEY`**. The default in **`scripts/deploy_ham_api_cloud_run.sh`** is:

   `CURSOR_API_KEY=ham-cursor-api-key:latest,HERMES_GATEWAY_API_KEY=ham-hermes-gateway-api-key:latest`

   If the Hermes secret is not created yet, either run **`scripts/seed_hermes_gateway_api_key.sh`** first, or set **`SET_SECRETS`** to only the secrets that exist, then add the Hermes pair after the secret exists.

3. Re-test **`POST /api/chat`** or the in-app chat: NDJSON and UI should no longer show **`Gateway HTTP 401`** when the key matches Hermes.

After deploy, Cloud Run prints the **service URL**.

## OpenRouter key (`OPENROUTER_API_KEY`)

- **Mount via Secret Manager** as **`OPENROUTER_API_KEY`** (see **`--set-secrets`** / **`--update-secrets`** above). The value must be **only** the raw key (**one line**, no `Bearer ` prefix, no shell commands). Pasting a whole terminal snippet into the secret produces **`UPSTREAM_REJECTED`** from OpenRouter; Ham also treats malformed values as **not chat-ready** in **`GET /api/models`** (see `openrouter_api_key_is_plausible` in `src/llm_client.py`).
- **`GET /api/models` with `openrouter_chat_ready: true`** means the key **looks** usable, not that billing/upstream is healthy—always smoke-test **`POST /api/chat`** after rotation.
- **Safe upload (no key on the shell command line):** create a file that contains **only** the key, then:

  ```bash
  gcloud secrets versions add ham-openrouter-api-key --data-file=./openrouter.key --project=PROJECT_ID
  gcloud run services update SERVICE --region=REGION --project=PROJECT_ID \
    --update-secrets=OPENROUTER_API_KEY=ham-openrouter-api-key:latest
  rm -f ./openrouter.key
  ```

  Edit **`openrouter.key`** with **`nano`** (or similar)—avoid **`cat <<EOF`** if you might paste more than the token. If **`cat`** is waiting for input, **Ctrl+C** cancels.
- **Stuck terminal:** **Ctrl+C** returns to the shell; delete any partial file and recreate the secret version from a clean one-line file.

## Private Hermes on GCE (HTTP gateway mode)

Use this when **Hermes Agent API** runs on a **private Compute Engine VM** and **Ham** on **Cloud Run** must call it over **RFC1918** addresses. The **browser never** calls Hermes; only Ham does.

### Hermes VM (operator)

- Run the **Hermes API server** on the VM; default listen port in docs is often **`8642`**.
- Bind to **`0.0.0.0:<port>`** (or the NIC that carries the **internal IP**), **not** `127.0.0.1` only, or Cloud Run cannot reach the service.
- Do **not** expose `<port>` to the public internet; restrict with VPC firewall.
- Store the API bearer token securely; the same value must appear as **`HERMES_GATEWAY_API_KEY`** on Ham (prefer **Secret Manager** on Cloud Run).

### Ham Cloud Run → VPC (operator)

**Preferred:** **Direct VPC egress** for Cloud Run — attach the service to your **VPC network** and subnet in the **same region** as the service (e.g. `us-west1`), with egress configured so **private IP** traffic reaches the VM subnet. Use **`private-ranges-only`** (or equivalent) if you want public URLs (e.g. model APIs) to use default internet egress while **10.0.0.0/8**, **172.16.0.0/12**, **192.168.0.0/16** go through the VPC.

**Fallback:** If Direct VPC egress is unavailable in your project/region, use a **Serverless VPC Access connector** in the same region and attach it to the Cloud Run service, with **`--vpc-egress private-ranges-only`** so traffic to the VM’s **internal IP** uses the VPC.

**Serverless VPC Access (concrete `gcloud` sequence):** (1) List subnets: `gcloud compute networks subnets list --network=default --project=PROJECT_ID` and pick a **dedicated `/28`** (e.g. `10.8.0.0/28`) that does **not** overlap any `RANGE` column. (2) Enable the API: `gcloud services enable vpcaccess.googleapis.com --project=PROJECT_ID`. (3) Create the connector in the **Cloud Run** region: `gcloud compute networks vpc-access connectors create ham-api-connector --region=us-central1 --network=default --range=10.8.0.0/28 --project=PROJECT_ID` (change **region** if your service is elsewhere; change **range** if it conflicts). (4) **Firewall** — create a rule that allows **`tcp:8642`** from the **same `/28`** in `--source-ranges` to the Hermes VM (use `--target-tags=hermes-api` on the rule and add that tag to the VM with `gcloud compute instances add-tags ...`). (5) Attach: `gcloud run services update ham-api --region=us-central1 --vpc-connector=ham-api-connector --vpc-egress=private-ranges-only --project=PROJECT_ID`. When you run **`gcloud run deploy`**, add the same **`--vpc-connector`** and **`--vpc-egress`** (plus **`--set-secrets`**, **`--env-vars-file`**) so the next revision does not drop networking.

### Firewall (operator)

- Allow **TCP** from the **Cloud Run egress path** (connector subnet or documented Serverless source ranges / your org standard) to the **VM internal IP** on **Hermes’ port**.
- Deny the same port from **`0.0.0.0/0`**.

### Ham env (repo + operator)

Set at least:

- `HERMES_GATEWAY_MODE=http`
- `HERMES_GATEWAY_BASE_URL=http://<VM_INTERNAL_IP>:8642` (or `http://<internal-dns>:8642`) — **no `/v1` suffix**
- `HERMES_GATEWAY_API_KEY` — **Secret Manager** reference on Cloud Run (recommended)
- `HERMES_GATEWAY_MODEL` — e.g. `hermes-agent` (must match Hermes server)

See commented template in [`docs/examples/ham-api-cloud-run-env.yaml`](examples/ham-api-cloud-run-env.yaml) and [`docs/HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md) (streaming **`stream: true`** behavior).

**Incident recovery:** if dashboard chat hangs or shows blank replies after model or gateway changes, align Cloud Run env with Hermes `config.yaml` using [`docs/RUNBOOK_HAM_MODEL_RECOVERY.md`](RUNBOOK_HAM_MODEL_RECOVERY.md).

## Smoke tests

```bash
curl -sS "${SERVICE_URL}/api/status"
curl -sS -X POST "${SERVICE_URL}/api/chat" \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"ping"}]}'
```

- If **`HERMES_GATEWAY_MODE=mock`**: assistant content typically contains **`Mock assistant reply`**.
- If **`HERMES_GATEWAY_MODE=http`** or **`openrouter`** with a working upstream: assistant content should **not** be the mock phrase; use **`scripts/verify_ham_api_deploy.sh`** (fails on accidental mock unless `HAM_VERIFY_ALLOW_MOCK=1`).

## In-app browser (Playwright) on Cloud Run

The **`/api/browser/*`** Playwright runtime remains available for **future workspace/desktop** consumers and integration tests; the legacy dashboard War Room UI was removed (Batch 2A). For Playwright to work **in production** (not just locally):

0. **One command (from repo root, after `gcloud` auth and `.gcloud/ham-api-env.yaml` exists):** run **`./scripts/deploy_ham_api_cloud_run.sh`** — Cloud Build, deploy, **`--memory 2Gi`**, and **`--cpu 2`** (overridable via `MEMORY` / `CPU` env). See the script header for `PROJECT_ID`, `SET_SECRETS`, etc.
1. **Rebuild and redeploy the API image** from the repo **`Dockerfile`**, which runs `python -m playwright install --with-deps chromium`. Older images that only `pip install playwright` have **no Chromium** — sessions will fail.
2. If you did **not** use the script, **raise Cloud Run memory** manually: e.g. **`gcloud run services update ham-api --memory 2Gi --region=REGION --project=PROJECT_ID`** (Chromium is heavy; 512Mi is often too small).
3. **CORS** must allow your Vercel origin (see **Wire the Vercel frontend** below) — the browser uses `fetch` to the API; wrong origins show **Failed to fetch** in DevTools, not a JSON error.
4. **Clerk / session:** the browser API uses the same **`Authorization: Bearer` (Clerk JWT)** as other dashboard routes when `HAM_CLERK_REQUIRE_AUTH` or `HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS` is on. The dashboard attaches this automatically; ensure **`VITE_CLERK_PUBLISHABLE_KEY`** is set on Vercel and users are signed in.
5. **Vercel:** **`VITE_HAM_API_BASE`** must point at this Cloud Run URL (rebuild after changing).

## Wire the Vercel frontend

1. In Vercel project env: **`VITE_HAM_API_BASE`** = Cloud Run URL (no trailing slash).
2. Redeploy the frontend (Vite bakes this at build time).
3. Ensure **`HAM_CORS_ORIGINS`** on Cloud Run includes your exact Vercel origin(s).
4. **Preview URLs:** each Vercel deployment gets a different hostname. Either add every preview origin to **`HAM_CORS_ORIGINS`**, or set **`HAM_CORS_ORIGIN_REGEX`** (e.g. `https://.*\.vercel\.app`) via the same env file and redeploy the service. Without a matching origin, the API may return **200** to `curl` but the **browser** will block the response (no `Access-Control-Allow-Origin`) → **Failed to fetch**.
5. **Packaged HAM Desktop (Linux/Windows):** the UI loads from **`file://`**, so browsers send **`Origin: null`**. Include the literal token **`null`** in **`HAM_CORS_ORIGINS`** (comma-separated) or the desktop app cannot use chat against this API. See **`docs/examples/ham-api-cloud-run-env.yaml`**.

## Local container (optional)

```bash
docker build -t ham-api:local .
docker run --rm -p 8080:8080 -e HERMES_GATEWAY_MODE=mock ham-api:local
curl -sS http://127.0.0.1:8080/api/status
```
