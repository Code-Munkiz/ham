#!/usr/bin/env bash
# Build the Ham API image (Playwright + Chromium) and deploy to Cloud Run with enough memory
# for headless browser sessions. Requires: gcloud auth, Artifact Registry, and Cloud Run.
#
#   export PROJECT_ID=your-gcp-project
#   ./scripts/deploy_ham_api_cloud_run.sh
#
# Optional: SKIP_BUILD=1  IMAGE_TAG=staging  REGION=us-central1  SERVICE=ham-api
# Optional: SET_SECRETS='CURSOR_API_KEY=ham-cursor-api-key:latest,OPENROUTER_API_KEY=ham-or-key:latest'
#
# Requires .gcloud/ham-api-env.yaml — copy from docs/examples/ham-api-cloud-run-env.yaml
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${PROJECT_ID:-clarity-staging-488201}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-ham-api}"
IMAGE_TAG="${IMAGE_TAG:-staging}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/ham/ham-api:${IMAGE_TAG}"
ENV_FILE="${ENV_FILE:-${ROOT}/.gcloud/ham-api-env.yaml}"
MEMORY="${MEMORY:-2Gi}"
CPU="${CPU:-2}"
SECRETS="${SET_SECRETS:-CURSOR_API_KEY=ham-cursor-api-key:latest}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE} — copy docs/examples/ham-api-cloud-run-env.yaml and edit. See docs/DEPLOY_CLOUD_RUN.md"
  exit 1
fi

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  echo "Building and pushing ${IMAGE} ..."
  gcloud builds submit --tag "${IMAGE}" . --project="${PROJECT_ID}"
else
  echo "SKIP_BUILD=1 — deploying image ${IMAGE}"
fi

echo "Deploying ${SERVICE} (memory ${MEMORY}, cpu ${CPU}) ..."

gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --project "${PROJECT_ID}" \
  --memory "${MEMORY}" \
  --cpu "${CPU}" \
  --env-vars-file "${ENV_FILE}" \
  --set-secrets="${SECRETS}"

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')"
echo ""
echo "=== Deployed: ${URL} ==="
echo "Vercel: set VITE_HAM_API_BASE=${URL} and redeploy. See scripts/deploy_ham_api_cloud_run.sh header."
