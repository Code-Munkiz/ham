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

## Smoke tests

```bash
curl -sS "${SERVICE_URL}/api/status"
curl -sS -X POST "${SERVICE_URL}/api/chat" \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"ping"}]}'
```

Expect **`mock`** mode: assistant content containing **`Mock assistant reply`**.

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
