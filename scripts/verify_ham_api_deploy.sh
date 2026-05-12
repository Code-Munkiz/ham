#!/usr/bin/env bash
# Smoke-test a deployed Ham API the way a browser does: status, CORS preflight, POST + ACAO.
# Usage:
#   ./scripts/verify_ham_api_deploy.sh 'https://YOUR-SERVICE-xxxxx.run.app' 'https://YOUR-PREVIEW.vercel.app'
# Second arg defaults to http://localhost:3000 (must be allowed by the API CORS config if testing a remote URL).
#
# When the API has HAM_CLERK_REQUIRE_AUTH=true, set a short-lived dashboard session JWT so agent + chat probes run:
#   HAM_VERIFY_CLERK_SESSION_JWT='eyJ...' ./scripts/verify_ham_api_deploy.sh 'https://YOUR-SERVICE.run.app' 'https://YOUR-PREVIEW.vercel.app'
# If unset and GET /api/projects/.../agents returns 401 CLERK_SESSION_REQUIRED, POST /api/chat checks are skipped after CORS preflight (partial OK).
#
# If the API should use a real upstream (Hermes http / OpenRouter), responses must NOT contain the mock phrase.
# Set HAM_VERIFY_ALLOW_MOCK=1 to skip that check (intentional mock deployments only).
set -euo pipefail

BASE="${1:?Usage: $0 <HAM_API_BASE_URL> [Origin URL]}"
ORIGIN="${2:-http://localhost:3000}"
BASE="${BASE%/}"

CLERK_AUTH_CURL=()
if [[ -n "${HAM_VERIFY_CLERK_SESSION_JWT:-}" ]]; then
  CLERK_AUTH_CURL=(-H "Authorization: Bearer ${HAM_VERIFY_CLERK_SESSION_JWT}")
fi
SKIP_CLERK_CHAT=0

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

# Workspace builder (Workbench): deployed OpenAPI must advertise full builder_sources surface; missing paths mean an old image even when /api/status is 200.
echo "== GET ${BASE}/openapi.json (workspace builder route parity)"
code_open="$(curl -sS -o "$body" -w '%{http_code}' "${BASE}/openapi.json")"
if [[ "$code_open" != "200" ]]; then
  echo "Expected HTTP 200 from openapi.json, got ${code_open}. Cannot verify builder parity." >&2
  exit 1
fi
VERIFY_OPENAPI_FILE="$body" python3 -c '
import importlib
import json
import os
from pathlib import Path

_sys = importlib.import_module("sys")
path = Path(os.environ["VERIFY_OPENAPI_FILE"])
data = json.loads(path.read_text(encoding="utf-8"))
openapi_paths = list((data.get("paths") or {}).keys())
path_keys = frozenset(openapi_paths)
required = (
    "/api/workspaces/{workspace_id}/builder/default-project",
    "/api/workspaces/{workspace_id}/projects/{project_id}/builder/activity/stream",
    "/api/workspaces/{workspace_id}/projects/{project_id}/builder/cloud-runtime",
)
missing = [r for r in required if r not in path_keys]
if missing:
    found_builder = sorted(p for p in openapi_paths if "/builder/" in p)
    print("Hosted API OpenAPI missing expected workspace-builder paths:", missing, file=_sys.stderr)
    print("Builder paths advertised on server (subset):", found_builder[:32], file=_sys.stderr)
    print("Fix: redeploy ham-api Docker image from current main so builder_sources routes are mounted.", file=_sys.stderr)
    raise SystemExit(1)
'
echo "openapi builder parity OK (default-project, activity/stream, cloud-runtime)"

echo "== GET ${BASE}/api/projects/__ham_deploy_verify__/agents (expect structured PROJECT_NOT_FOUND 404)"
code_agents="$(curl -sS -o "$body" -w '%{http_code}' "${CLERK_AUTH_CURL[@]}" "${BASE}/api/projects/__ham_deploy_verify__/agents")"
if [[ "$code_agents" == "404" ]]; then
  if ! grep -q "PROJECT_NOT_FOUND" "$body"; then
    echo "Agent Builder route missing or wrong API: expected JSON with PROJECT_NOT_FOUND, got:" >&2
    cat "$body" >&2 || true
    echo >&2
    echo "If body is {\"detail\":\"Not Found\"}, the running image has no GET /api/projects/{{id}}/agents — rebuild/redeploy. Also set VITE_HAM_API_BASE to the API origin only (no /api suffix)." >&2
    exit 1
  fi
elif [[ "$code_agents" == "401" ]] && grep -q "CLERK_SESSION_REQUIRED" "$body"; then
  if [[ -n "${HAM_VERIFY_CLERK_SESSION_JWT:-}" ]]; then
    echo "Expected 404 after Clerk auth, got 401. Body:" >&2
    cat "$body" >&2 || true
    exit 1
  fi
  echo "WARN: Clerk auth required (CLERK_SESSION_REQUIRED); skipping agent + chat POST probes." >&2
  echo "       Re-run with HAM_VERIFY_CLERK_SESSION_JWT='<Clerk session JWT>' for full checks." >&2
  SKIP_CLERK_CHAT=1
else
  echo "Unexpected HTTP ${code_agents} for unknown project_id agents probe. Body:" >&2
  cat "$body" >&2 || true
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

# Dashboard Workspace chat uses POST /api/chat/stream — preflight should succeed before authenticated POST probes.
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

if [[ "$SKIP_CLERK_CHAT" == "1" ]]; then
  echo "Partial OK (status + OpenAPI builder parity + OPTIONS CORS for /api/chat and /api/chat/stream)."
  exit 0
fi

echo "== POST ${BASE}/api/chat (Origin: ${ORIGIN})"
code_post="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' \
    "${CLERK_AUTH_CURL[@]}" \
    -X POST "${BASE}/api/chat" \
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

echo "== POST ${BASE}/api/chat/stream (Origin + Accept — matches browser)"
code_stream="$(
  curl -sS --max-time 120 -D "$hdrs" -o "$body" -w '%{http_code}' \
    "${CLERK_AUTH_CURL[@]}" \
    -X POST "${BASE}/api/chat/stream" \
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
