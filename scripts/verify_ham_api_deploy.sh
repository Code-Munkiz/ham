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

# Dashboard Chat.tsx calls POST /api/chat/stream (NDJSON), not only /api/chat.
echo "== OPTIONS ${BASE}/api/chat/stream (preflight, Origin: ${ORIGIN}, headers: content-type + accept)"
code_so="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' -X OPTIONS "${BASE}/api/chat/stream" \
    -H "Origin: ${ORIGIN}" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: content-type, accept"
)"
if [[ "$code_so" != "200" ]]; then
  echo "OPTIONS /api/chat/stream expected HTTP 200, got ${code_so}. Body:" >&2
  cat "$body" >&2 || true
  exit 1
fi
acao_so="$(grep -i '^access-control-allow-origin:' "$hdrs" | tr -d '\r' || true)"
if [[ -z "$acao_so" ]]; then
  echo "Missing Access-Control-Allow-Origin on OPTIONS /api/chat/stream." >&2
  exit 1
fi
echo "$acao_so"

echo "== POST ${BASE}/api/chat/stream (Origin + Accept — matches browser)"
code_stream="$(
  curl -sS --max-time 120 -D "$hdrs" -o "$body" -w '%{http_code}' -X POST "${BASE}/api/chat/stream" \
    -H "Origin: ${ORIGIN}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/x-ndjson, application/json" \
    -d '{"messages":[{"role":"user","content":"deploy verify stream"}]}'
)"
stream_acao="$(grep -i '^access-control-allow-origin:' "$hdrs" | tr -d '\r' || true)"
if [[ "$code_stream" != "200" ]]; then
  echo "POST /api/chat/stream returned HTTP ${code_stream} (dashboard chat uses this endpoint)." >&2
  echo "If this is 404, your Cloud Run image is likely older than the repo — rebuild and redeploy the API." >&2
  cat "$body" >&2 || true
  exit 1
fi
if [[ -z "$stream_acao" ]]; then
  echo "Missing Access-Control-Allow-Origin on POST /api/chat/stream." >&2
  exit 1
fi
echo "$stream_acao"
first="$(head -n 1 "$body")"
if [[ "$first" != *"session"* ]]; then
  echo "Expected first NDJSON line to be a session event, got: ${first:0:120}" >&2
  exit 1
fi
echo "Stream body (first line): ${first:0:120}..."
echo "OK"
