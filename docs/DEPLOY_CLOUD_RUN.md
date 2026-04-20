# Deploy Ham API to Google Cloud Run

This repo ships a **`Dockerfile`** that runs **`uvicorn src.api.server:app`**. The browser never talks to Cloud Run with vendor gateway paths; only Ham routes like **`POST /api/chat`**.

**End-to-end checklist (Vercel + GCP):** [`docs/DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md). After deploy, run **`scripts/verify_ham_api_deploy.sh`** with your API URL and the **exact** Vercel `Origin` you use in the browser.

## What you do in GCP (not automatable from this repo)

1. Pick or create a **GCP project** (e.g. staging).
2. Enable billing if required.
3. Enable APIs (Console or `gcloud`):
   - **Cloud Run Admin API**
   - **Artifact Registry API**
   - **Cloud Build API** (if you use `gcloud builds submit`)
4. Choose a **region** (e.g. `us-central1`).
5. Create an **Artifact Registry** Docker repository (one-time), e.g. `ham`.
6. **Deploy** the image and set **environment variables** / secrets (see below).
7. Note the **service URL** (e.g. `https://ham-api-staging-xxxxx-uc.a.run.app`) for **`VITE_HAM_API_BASE`** on Vercel.

IAM: start with **allow unauthenticated invoke** for a quick staging smoke test, or use **IAM** + **identity tokens** / API keys later.

## One-time: Artifact Registry

Replace `PROJECT_ID`, `REGION`, and repo name `ham` as needed.

```bash
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories create ham \
  --repository-format=docker \
  --location=REGION \
  --description="Ham API images"
```

## Build and push the image

From the **repository root** (where this `Dockerfile` lives):

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/ham/ham-api:staging"

gcloud builds submit --tag "${IMAGE}" .
```

## Deploy to Cloud Run

```bash
export SERVICE=ham-api-staging

# Prefer an env YAML file: commas in HAM_CORS_ORIGINS break `--set-env-vars` parsing.
# Copy `docs/examples/ham-api-cloud-run-env.yaml` to `.gcloud/ham-api-env.yaml` (gitignored) and edit.

gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --env-vars-file .gcloud/ham-api-env.yaml
```

Add more env vars as needed, e.g. **`HERMES_GATEWAY_MODE=http`**, **`HERMES_GATEWAY_BASE_URL`**, **`HERMES_GATEWAY_API_KEY`**, **`OPENROUTER_API_KEY`** (use **Secret Manager** for secrets in real deployments).

After deploy, Cloud Run prints the **service URL**.

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

## Smoke tests

```bash
curl -sS "${SERVICE_URL}/api/status"
curl -sS -X POST "${SERVICE_URL}/api/chat" \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"ping"}]}'
```

- If **`HERMES_GATEWAY_MODE=mock`**: assistant content typically contains **`Mock assistant reply`**.
- If **`HERMES_GATEWAY_MODE=http`** or **`openrouter`** with a working upstream: assistant content should **not** be the mock phrase; use **`scripts/verify_ham_api_deploy.sh`** (fails on accidental mock unless `HAM_VERIFY_ALLOW_MOCK=1`).

## Wire the Vercel frontend

1. In Vercel project env: **`VITE_HAM_API_BASE`** = Cloud Run URL (no trailing slash).
2. Redeploy the frontend (Vite bakes this at build time).
3. Ensure **`HAM_CORS_ORIGINS`** on Cloud Run includes your exact Vercel origin(s).
4. **Preview URLs:** each Vercel deployment gets a different hostname. Either add every preview origin to **`HAM_CORS_ORIGINS`**, or set **`HAM_CORS_ORIGIN_REGEX`** (e.g. `https://.*\.vercel\.app`) via the same env file and redeploy the service. Without a matching origin, the API may return **200** to `curl` but the **browser** will block the response (no `Access-Control-Allow-Origin`) → **Failed to fetch**.

## Local container (optional)

```bash
docker build -t ham-api:local .
docker run --rm -p 8080:8080 -e HERMES_GATEWAY_MODE=mock ham-api:local
curl -sS http://127.0.0.1:8080/api/status
```
