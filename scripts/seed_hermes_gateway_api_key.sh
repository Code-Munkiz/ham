#!/usr/bin/env bash
# One-time: store Hermes API key in Secret Manager and grant the default Compute Engine
# service account access (same pattern as ham-cursor-api-key / docs/DEPLOY_CLOUD_RUN.md).
#
# The value must be the *same* token Hermes expects (Authorization: Bearer) — often
# API_SERVER_KEY on the Hermes host. Fix "Gateway HTTP 401" when HERMES_GATEWAY_MODE=http.
#
# Usage:
#   export PROJECT_ID=clarity-staging-488201
#   printf '%s' 'YOUR_PLAINTEXT_KEY' | ./scripts/seed_hermes_gateway_api_key.sh
# Or:
#   ./scripts/seed_hermes_gateway_api_key.sh ./path/to/one_line_key.txt
#
# After this, deploy Cloud Run with HERMES_GATEWAY_API_KEY mounted, e.g.:
#   export SET_SECRETS='CURSOR_API_KEY=ham-cursor-api-key:latest,HERMES_GATEWAY_API_KEY=ham-hermes-gateway-api-key:latest'
#   ./scripts/deploy_ham_api_cloud_run.sh
set -euo pipefail
SECRET_ID="${HERMES_SECRET_ID:-ham-hermes-gateway-api-key}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_ID="${PROJECT_ID:-}"
if [[ -z "${PROJECT_ID}" ]]; then
  echo "Set PROJECT_ID (e.g. export PROJECT_ID=clarity-staging-488201)"
  exit 1
fi

if [[ -n "${1:-}" ]]; then
  DATA_FILE="$1"
  if [[ ! -f "$DATA_FILE" ]]; then
    echo "File not found: $DATA_FILE"
    exit 1
  fi
else
  mkdir -p "${ROOT}/.gcloud"
  DATA_FILE="${ROOT}/.gcloud/.hermes_gateway_key_one_time"
  echo "Reading key from stdin (one line, no extra newline if possible)..."
  cat > "${DATA_FILE}"
  trap 'rm -f "${DATA_FILE}"' EXIT
fi

if gcloud secrets describe "${SECRET_ID}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "Secret ${SECRET_ID} exists; adding new version..."
  gcloud secrets versions add "${SECRET_ID}" --data-file="${DATA_FILE}" --project="${PROJECT_ID}"
else
  echo "Creating secret ${SECRET_ID}..."
  gcloud secrets create "${SECRET_ID}" --data-file="${DATA_FILE}" --project="${PROJECT_ID}" --replication-policy=automatic
fi

# Default Cloud Run runtime SA: PROJECT_NUMBER-compute@developer.gserviceaccount.com
PN="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
SA="${PN}-compute@developer.gserviceaccount.com"
echo "Binding Secret Accessor for ${SA} on ${SECRET_ID}..."
gcloud secrets add-iam-policy-binding "${SECRET_ID}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet

echo ""
echo "=== Done. Mount on Cloud Run as env HERMES_GATEWAY_API_KEY from secret ${SECRET_ID}."
echo "Example deploy (also rebuilds/pushes image unless SKIP_BUILD=1):"
echo "  export PROJECT_ID=${PROJECT_ID}"
echo "  export SET_SECRETS='CURSOR_API_KEY=ham-cursor-api-key:latest,HERMES_GATEWAY_API_KEY=${SECRET_ID}:latest'"
echo "  ${ROOT}/scripts/deploy_ham_api_cloud_run.sh"
