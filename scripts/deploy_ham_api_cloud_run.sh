#!/usr/bin/env bash
# Build the Ham API image (Playwright + Chromium) and deploy to Cloud Run with enough memory
# for headless browser sessions. Requires: gcloud auth, Artifact Registry, and Cloud Run.
#
#   export PROJECT_ID=your-gcp-project
#   ./scripts/deploy_ham_api_cloud_run.sh
#
# Optional: SKIP_BUILD=1  IMAGE_TAG=staging  REGION=us-central1  SERVICE=ham-api
# Optional: SET_SECRETS (comma-separated). Defaults include Hermes gateway key for http mode.
#   HERMES_GATEWAY_API_KEY must exist in Secret Manager (see scripts/seed_hermes_gateway_api_key.sh).
#   Example override: SET_SECRETS='CURSOR_API_KEY=ham-cursor-api-key:latest,OPENROUTER_API_KEY=...'
#
# Required-secrets guardrail:
#   `gcloud run deploy --set-secrets=...` REPLACES the revision's secret env set; any required env
#   name not listed is silently dropped on the new revision. To prevent accidental regressions
#   (e.g. losing HAM_DROID_RUNNER_TOKEN -> remote Factory Droid runner offline), this script
#   refuses to deploy unless every name in REQUIRED_SECRET_ENVS appears as a left-hand env
#   binding in the resolved SECRETS string. To bypass (NOT recommended), set ALLOW_SECRET_DROP=1.
#   HAM_DROID_EXEC_TOKEN is intentionally NOT required yet: it is reserved for the future
#   Factory Droid Build Lane mutation gate and is not used by any live route today.
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
# CURSOR + Hermes (http gateway) + Cloud Agent launch gate + Factory Droid remote runner bearer.
# Create secrets first or deploy will fail on missing ids.
# ham-cursor-agent-launch-token → HAM_CURSOR_AGENT_LAUNCH_TOKEN (see docs/DEPLOY_CLOUD_RUN.md).
# ham-droid-runner-token → HAM_DROID_RUNNER_TOKEN (Cloud Run bearer to ham-droid-runner-1 RFC1918 host).
# ham-opencode-exec-token → HAM_OPENCODE_EXEC_TOKEN (OpenCode build/launch Bearer gate).
SECRETS="${SET_SECRETS:-CURSOR_API_KEY=ham-cursor-api-key:latest,HERMES_GATEWAY_API_KEY=ham-hermes-gateway-api-key:latest,HAM_CURSOR_AGENT_LAUNCH_TOKEN=ham-cursor-agent-launch-token:latest,HAM_TRANSCRIPTION_API_KEY=ham-transcription-api-key:latest,HAM_DROID_RUNNER_TOKEN=ham-droid-runner-token:latest,HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY=ham-connected-tools-credential-encryption-key:latest,HAM_OPENCODE_EXEC_TOKEN=ham-opencode-exec-token:latest}"

# Guardrail: required secret env bindings that MUST appear in the resolved SECRETS string.
# Adding a new required name here will block future deploys until the operator wires the secret.
# HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY -> ham-connected-tools-credential-encryption-key:
# Fernet key for BYOK Connected Tools persistence; dropping it silently breaks workspace tool
# credential storage on the new revision.
REQUIRED_SECRET_ENVS=(
  CURSOR_API_KEY
  HERMES_GATEWAY_API_KEY
  HAM_CURSOR_AGENT_LAUNCH_TOKEN
  HAM_TRANSCRIPTION_API_KEY
  HAM_DROID_RUNNER_TOKEN
  HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY
  HAM_OPENCODE_EXEC_TOKEN
)

if [[ "${ALLOW_SECRET_DROP:-0}" != "1" ]]; then
  missing=()
  # Wrap SECRETS in commas so we can match `,<NAME>=` at any position (start, middle, end).
  _padded=",${SECRETS},"
  for _name in "${REQUIRED_SECRET_ENVS[@]}"; do
    if [[ "${_padded}" != *",${_name}="* ]]; then
      missing+=("${_name}")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    echo "ERROR: --set-secrets is missing required env bindings: ${missing[*]}" >&2
    echo "" >&2
    echo "  Cloud Run --set-secrets REPLACES the revision's secret env set." >&2
    echo "  Any required env name not listed here is silently dropped on the new revision," >&2
    echo "  breaking dependent features (e.g. HAM_DROID_RUNNER_TOKEN -> remote Factory Droid runner)." >&2
    echo "" >&2
    echo "  Fix: pass SET_SECRETS covering every required name, e.g." >&2
    echo "    SET_SECRETS='CURSOR_API_KEY=ham-cursor-api-key:latest,\\" >&2
    echo "                 HERMES_GATEWAY_API_KEY=ham-hermes-gateway-api-key:latest,\\" >&2
    echo "                 HAM_CURSOR_AGENT_LAUNCH_TOKEN=ham-cursor-agent-launch-token:latest,\\" >&2
    echo "                 HAM_TRANSCRIPTION_API_KEY=ham-transcription-api-key:latest,\\" >&2
    echo "                 HAM_DROID_RUNNER_TOKEN=ham-droid-runner-token:latest,\\" >&2
    echo "                 HAM_CONNECTED_TOOLS_CREDENTIAL_ENCRYPTION_KEY=ham-connected-tools-credential-encryption-key:latest,\\" >&2
    echo "                 HAM_OPENCODE_EXEC_TOKEN=ham-opencode-exec-token:latest'" >&2
    echo "" >&2
    echo "  Or rely on the script default by leaving SET_SECRETS unset." >&2
    echo "" >&2
    echo "  Override (NOT recommended): re-run with ALLOW_SECRET_DROP=1 to bypass this guardrail." >&2
    exit 2
  fi
else
  echo "WARNING: ALLOW_SECRET_DROP=1 set; skipping required-secrets guardrail." >&2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE} — copy docs/examples/ham-api-cloud-run-env.yaml and edit. See docs/DEPLOY_CLOUD_RUN.md"
  exit 1
fi
# Reminder: --env-vars-file replaces the revision's plain env vars entirely; do not deploy a mock-only
# YAML to staging if the service must use HERMES_GATEWAY_MODE=http or openrouter (see DEPLOY_CLOUD_RUN.md).

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
