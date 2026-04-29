#!/usr/bin/env bash
# One-time: store OpenAI API key for POST /api/chat/transcribe in Secret Manager and grant
# the default Compute Engine service account access (same pattern as other ham-* secrets).
#
# Usage:
#   export PROJECT_ID=clarity-staging-488201
#   printf '%s' 'YOUR_OPENAI_API_KEY' | ./scripts/seed_ham_transcription_api_key.sh
# Or:
#   ./scripts/seed_ham_transcription_api_key.sh ./path/to/one_line_key.txt
#
# Then redeploy ham-api with SET_SECRETS including HAM_TRANSCRIPTION_API_KEY=ham-transcription-api-key:latest
set -euo pipefail
SECRET_ID="${HAM_TRANSCRIPTION_SECRET_ID:-ham-transcription-api-key}"
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
  DATA_FILE="${ROOT}/.gcloud/.ham_transcription_key_one_time"
  echo "Reading OpenAI API key from stdin (one line)..."
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
echo "=== Done. Mount on Cloud Run as env HAM_TRANSCRIPTION_API_KEY from secret ${SECRET_ID}."
echo "Use deploy script defaults or extend SET_SECRETS with HAM_TRANSCRIPTION_API_KEY=${SECRET_ID}:latest"
echo "  export PROJECT_ID=${PROJECT_ID}"
echo "  ${ROOT}/scripts/deploy_ham_api_cloud_run.sh"
