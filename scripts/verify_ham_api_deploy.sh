#!/usr/bin/env bash
# Smoke-test a deployed Ham API the way a browser does: status, CORS preflight, POST + ACAO.
# Usage:
#   ./scripts/verify_ham_api_deploy.sh 'https://YOUR-SERVICE-xxxxx.run.app' 'https://YOUR-PREVIEW.vercel.app'
# Second arg defaults to http://localhost:3000 (must be allowed by the API CORS config if testing a remote URL).
#
# If the API should use a real upstream (Hermes http / OpenRouter), responses must NOT contain the mock phrase.
# Set HAM_VERIFY_ALLOW_MOCK=1 to skip that check (intentional mock deployments only).
set -euo pipefail

BASE="${1:?Usage: $0 <HAM_API_BASE_URL> [Origin URL]}"
ORIGIN="${2:-http://localhost:3000}"
BASE="${BASE%/}"

hdrs="$(mktemp)"
body="$(mktemp)"
trap 'rm -f "$hdrs" "$body"' EXIT

echo "== GET ${BASE}/api/status"
status_body="$(curl -sS -f "${BASE}/api/status")"
echo "HTTP 200 (body length ${#status_body})"
if ! STATUS_BODY="$status_body" python3 -c '
import json, os, sys
d = json.loads(os.environ["STATUS_BODY"])
cap = d.get("capabilities") or {}
if cap.get("project_agent_profiles_read") is not True:
    print("Missing capabilities.project_agent_profiles_read=true — redeploy Ham API from current main.", file=sys.stderr)
    sys.exit(1)
' 2>/dev/null; then
  echo "Capability check failed. Body:" >&2
  echo "$status_body" >&2
  exit 1
fi

echo "== GET ${BASE}/api/projects/__ham_deploy_verify__/agents (expect structured PROJECT_NOT_FOUND 404)"
code_agents="$(curl -sS -o "$body" -w '%{http_code}' "${BASE}/api/projects/__ham_deploy_verify__/agents")"
if [[ "$code_agents" != "404" ]]; then
  echo "Expected HTTP 404 for unknown project_id, got ${code_agents}. Body:" >&2
  cat "$body" >&2 || true
  exit 1
fi
if ! grep -q "PROJECT_NOT_FOUND" "$body"; then
  echo "Agent Builder route missing or wrong API: expected JSON with PROJECT_NOT_FOUND, got:" >&2
  cat "$body" >&2 || true
  echo >&2
  echo "If body is {\"detail\":\"Not Found\"}, the running image has no GET /api/projects/{{id}}/agents — rebuild/redeploy. Also set VITE_HAM_API_BASE to the API origin only (no /api suffix)." >&2
  exit 1
fi

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
if [[ -z "${HAM_VERIFY_ALLOW_MOCK:-}" ]] && grep -q "Mock assistant reply" "$body"; then
  echo "Chat returned mock-mode text (substring: Mock assistant reply)." >&2
  echo "Staging/prod should use HERMES_GATEWAY_MODE=http or openrouter with a working upstream." >&2
  echo "If this service is intentionally mock, re-run with: HAM_VERIFY_ALLOW_MOCK=1 $0 ..." >&2
  exit 1
fi

# Dashboard Workspace chat calls POST /api/chat/stream (NDJSON), not only /api/chat.
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
if [[ -z "${HAM_VERIFY_ALLOW_MOCK:-}" ]] && grep -q "Mock assistant reply" "$body"; then
  echo "Stream response contained mock-mode text (substring: Mock assistant reply)." >&2
  echo "Staging/prod should use HERMES_GATEWAY_MODE=http or openrouter with a working upstream." >&2
  echo "If this service is intentionally mock, re-run with: HAM_VERIFY_ALLOW_MOCK=1 $0 ..." >&2
  exit 1
fi
echo "OK"
