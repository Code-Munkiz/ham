#!/usr/bin/env bash
# Hosted workspace smoke checks (Clerk + Firestore path).
# Verifies read/create/list/access-deny behavior without mutating deployment config.
#
# Inputs (env-first, positional fallback):
#   HAM_API_BASE or API or $1
#   HAM_WEB_ORIGIN or ORIGIN or $2 (default: http://localhost:3000)
#   TOKEN_A or $3  (Clerk session JWT for user A)
#   TOKEN_B or $4  (Clerk session JWT for user B)
#
# Example:
#   HAM_API_BASE="https://ham-api-xxxxx.run.app" \
#   HAM_WEB_ORIGIN="https://your-app.vercel.app" \
#   TOKEN_A="eyJ..." TOKEN_B="eyJ..." \
#   bash scripts/verify_workspace_hosted_smoke.sh
set -euo pipefail

BASE="${HAM_API_BASE:-${API:-${1:-}}}"
ORIGIN_INPUT="${HAM_WEB_ORIGIN:-${ORIGIN:-${2:-http://localhost:3000}}}"
TOKEN_A_INPUT="${TOKEN_A:-${3:-}}"
TOKEN_B_INPUT="${TOKEN_B:-${4:-}}"

usage() {
  cat >&2 <<'EOF'
Usage:
  HAM_API_BASE=<https://api.run.app> HAM_WEB_ORIGIN=<https://app.vercel.app> TOKEN_A=<jwt> TOKEN_B=<jwt> \
    bash scripts/verify_workspace_hosted_smoke.sh

Inputs:
  HAM_API_BASE (or API)    Required. API origin (no trailing slash required).
  HAM_WEB_ORIGIN (or ORIGIN) Optional. Browser Origin for CORS checks (default http://localhost:3000).
  TOKEN_A                  Required. Clerk session JWT for user A.
  TOKEN_B                  Required. Clerk session JWT for user B.
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

mask_token() {
  local token="$1"
  local n="${#token}"
  if (( n < 12 )); then
    printf '<redacted>'
    return
  fi
  printf '%s...%s' "${token:0:6}" "${token: -4}"
}

log_auth() {
  local label="$1"
  local token="$2"
  echo "  ${label} Authorization: Bearer $(mask_token "$token")"
}

if [[ -z "$BASE" ]]; then
  echo "Missing HAM_API_BASE/API (or positional \$1)." >&2
  usage
  exit 1
fi
if [[ -z "$TOKEN_A_INPUT" || -z "$TOKEN_B_INPUT" ]]; then
  echo "Missing TOKEN_A and/or TOKEN_B." >&2
  usage
  exit 1
fi

require_cmd curl
require_cmd jq

BASE="${BASE%/}"
ORIGIN="$ORIGIN_INPUT"
TOKEN_A="$TOKEN_A_INPUT"
TOKEN_B="$TOKEN_B_INPUT"

hdrs="$(mktemp)"
body="$(mktemp)"
trap 'rm -f "$hdrs" "$body"' EXIT

echo "== Hosted workspace smoke =="
echo "API: ${BASE}"
echo "Origin: ${ORIGIN}"
echo "Token A: $(mask_token "$TOKEN_A")"
echo "Token B: $(mask_token "$TOKEN_B")"
echo "Tokens are redacted in output."

echo
echo "== 1) CORS preflight /api/me"
code_preflight="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' -X OPTIONS "${BASE}/api/me" \
    -H "Origin: ${ORIGIN}" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: authorization"
)"
if [[ "$code_preflight" != "200" ]]; then
  echo "CORS preflight failed for /api/me (HTTP ${code_preflight})." >&2
  cat "$body" >&2 || true
  exit 1
fi
acao="$(awk 'BEGIN{IGNORECASE=1}/^access-control-allow-origin:/{sub(/\r$/,"");print;exit}' "$hdrs")"
if [[ -z "$acao" ]]; then
  echo "Missing Access-Control-Allow-Origin on /api/me preflight." >&2
  exit 1
fi
echo "$acao"

echo
echo "== 2) GET /api/me as user A (expect auth_mode=clerk)"
log_auth "User A" "$TOKEN_A"
code_me_a="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' "${BASE}/api/me" \
    -H "Origin: ${ORIGIN}" \
    -H "Authorization: Bearer ${TOKEN_A}"
)"
if [[ "$code_me_a" != "200" ]]; then
  echo "GET /api/me failed for user A (HTTP ${code_me_a})." >&2
  cat "$body" >&2 || true
  exit 1
fi
auth_mode_a="$(jq -r '.auth_mode // ""' "$body")"
user_a_id="$(jq -r '.user.user_id // ""' "$body")"
if [[ "$auth_mode_a" != "clerk" ]]; then
  echo "Expected auth_mode=clerk for user A, got: ${auth_mode_a:-<empty>}." >&2
  cat "$body" >&2 || true
  exit 1
fi
if [[ -z "$user_a_id" ]]; then
  echo "Missing user.user_id in /api/me response for user A." >&2
  cat "$body" >&2 || true
  exit 1
fi
echo "User A id: ${user_a_id}"

echo
echo "== 3) GET /api/workspaces as user A"
log_auth "User A" "$TOKEN_A"
code_list_a_before="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' "${BASE}/api/workspaces" \
    -H "Origin: ${ORIGIN}" \
    -H "Authorization: Bearer ${TOKEN_A}"
)"
if [[ "$code_list_a_before" != "200" ]]; then
  echo "GET /api/workspaces failed for user A (HTTP ${code_list_a_before})." >&2
  cat "$body" >&2 || true
  exit 1
fi
count_before="$(jq -r '.workspaces | length' "$body" 2>/dev/null || echo "0")"
echo "User A workspaces before create: ${count_before}"

echo
echo "== 4) POST /api/workspaces create personal workspace as user A"
workspace_name="hosted-smoke-$(date +%s)"
create_payload="$(jq -nc --arg name "$workspace_name" '{"name": $name}')"
log_auth "User A" "$TOKEN_A"
code_create="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' -X POST "${BASE}/api/workspaces" \
    -H "Origin: ${ORIGIN}" \
    -H "Authorization: Bearer ${TOKEN_A}" \
    -H "Content-Type: application/json" \
    -d "$create_payload"
)"
if [[ "$code_create" != "201" ]]; then
  echo "POST /api/workspaces failed for user A (HTTP ${code_create})." >&2
  cat "$body" >&2 || true
  exit 1
fi
workspace_id="$(jq -r '.workspace.workspace_id // ""' "$body")"
if [[ -z "$workspace_id" ]]; then
  echo "POST /api/workspaces succeeded but workspace_id was missing." >&2
  cat "$body" >&2 || true
  exit 1
fi
echo "Created workspace_id: ${workspace_id}"

echo
echo "== 5) GET /api/workspaces confirms persistence for user A"
log_auth "User A" "$TOKEN_A"
code_list_a_after="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' "${BASE}/api/workspaces" \
    -H "Origin: ${ORIGIN}" \
    -H "Authorization: Bearer ${TOKEN_A}"
)"
if [[ "$code_list_a_after" != "200" ]]; then
  echo "GET /api/workspaces (post-create) failed for user A (HTTP ${code_list_a_after})." >&2
  cat "$body" >&2 || true
  exit 1
fi
present="$(jq -r --arg wid "$workspace_id" 'any(.workspaces[]?; .workspace_id == $wid)' "$body")"
if [[ "$present" != "true" ]]; then
  echo "Created workspace_id not found in user A list response." >&2
  cat "$body" >&2 || true
  exit 1
fi
echo "Workspace persists in list response."

echo
echo "== 6) User B cannot access user A personal workspace"
log_auth "User B" "$TOKEN_B"
code_get_b="$(
  curl -sS -D "$hdrs" -o "$body" -w '%{http_code}' "${BASE}/api/workspaces/${workspace_id}" \
    -H "Origin: ${ORIGIN}" \
    -H "Authorization: Bearer ${TOKEN_B}"
)"
if [[ "$code_get_b" == "200" ]]; then
  echo "Isolation failure: user B was able to read user A workspace." >&2
  cat "$body" >&2 || true
  exit 1
fi
if [[ "$code_get_b" != "403" && "$code_get_b" != "404" ]]; then
  echo "Unexpected status for user B workspace access: HTTP ${code_get_b} (expected 403/404)." >&2
  cat "$body" >&2 || true
  exit 1
fi
err_code="$(jq -r '.detail.error.code // .error.code // empty' "$body" 2>/dev/null || true)"
if [[ -n "$err_code" ]]; then
  echo "User B denied as expected (HTTP ${code_get_b}, code ${err_code})."
else
  echo "User B denied as expected (HTTP ${code_get_b})."
fi

echo
echo "OK: hosted workspace smoke checks passed."
