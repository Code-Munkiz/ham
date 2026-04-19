#!/usr/bin/env bash
# Smoke-test a deployed Ham API the way a browser does: status, CORS preflight, POST + ACAO.
# Usage:
#   ./scripts/verify_ham_api_deploy.sh 'https://YOUR-SERVICE-xxxxx.run.app' 'https://YOUR-PREVIEW.vercel.app'
# Second arg defaults to http://localhost:3000 (must be allowed by the API CORS config if testing a remote URL).
set -euo pipefail

BASE="${1:?Usage: $0 <HAM_API_BASE_URL> [Origin URL]}"
ORIGIN="${2:-http://localhost:3000}"
BASE="${BASE%/}"

hdrs="$(mktemp)"
body="$(mktemp)"
trap 'rm -f "$hdrs" "$body"' EXIT

echo "== GET ${BASE}/api/status"
curl -sS -f -o /dev/null -w "HTTP %{http_code}\n" "${BASE}/api/status"

echo "== OPTIONS ${BASE}/api/chat (preflight, Origin: ${ORIGIN})"
code="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' -X OPTIONS "${BASE}/api/chat" \
    -H "Origin: ${ORIGIN}" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: content-type"
)"
acao="$(grep -i '^access-control-allow-origin:' "$hdrs" | tr -d '\r' || true)"
if [[ "$code" != "200" ]]; then
  echo "Expected HTTP 200 from OPTIONS, got ${code}. Body:" >&2
  cat "$body" >&2 || true
  echo >&2
  echo "Fix: allow this Origin via HAM_CORS_ORIGINS or HAM_CORS_ORIGIN_REGEX (see docs/examples/ham-api-cloud-run-env.yaml)." >&2
  exit 1
fi
if [[ -z "$acao" ]]; then
  echo "Missing Access-Control-Allow-Origin on OPTIONS — browsers will block the request." >&2
  exit 1
fi
echo "$acao"

echo "== POST ${BASE}/api/chat (Origin: ${ORIGIN})"
code_post="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' -X POST "${BASE}/api/chat" \
    -H "Origin: ${ORIGIN}" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"deploy verify"}]}'
)"
post_acao="$(grep -i '^access-control-allow-origin:' "$hdrs" | tr -d '\r' || true)"
if [[ "$code_post" != "200" ]]; then
  echo "POST returned HTTP ${code_post}. Body:" >&2
  cat "$body" >&2 || true
  exit 1
fi
if [[ -z "$post_acao" ]]; then
  echo "Missing Access-Control-Allow-Origin on POST — browsers will hide the response body." >&2
  exit 1
fi
echo "$post_acao"
echo "Body (preview): $(head -c 160 "$body")..."
echo "OK"
