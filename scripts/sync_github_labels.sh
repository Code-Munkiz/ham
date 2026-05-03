#!/usr/bin/env bash
#
# Idempotent GitHub label sync for HAM.
#
# Re-run any time the taxonomy changes; `gh label create --force` updates the
# color and description on existing labels rather than failing. Existing
# default labels (bug, enhancement, etc.) are NOT modified — they coexist
# with the prefixed taxonomy below.
#
# Usage:
#   ./scripts/sync_github_labels.sh                         # uses current gh repo
#   ./scripts/sync_github_labels.sh --repo Code-Munkiz/ham  # explicit
#
# Requires: gh CLI authenticated with `repo` scope (issues: write).

set -euo pipefail

REPO_FLAG=()
if [[ "${1:-}" == "--repo" && -n "${2:-}" ]]; then
  REPO_FLAG=(--repo "$2")
fi

create_or_update() {
  local name="$1" color="$2" description="$3"
  echo "  syncing: ${name}"
  gh label create "${name}" \
    --color "${color}" \
    --description "${description}" \
    --force \
    "${REPO_FLAG[@]}" >/dev/null
}

echo "==> priority"
create_or_update "priority:P0" "b60205" "Drop-everything; production down or active security incident"
create_or_update "priority:P1" "d93f0b" "Ship within the week; active user/customer impact"
create_or_update "priority:P2" "fbca04" "Plan within the current quarter"
create_or_update "priority:P3" "c5def5" "Backlog; nice-to-have"

echo "==> severity"
create_or_update "severity:critical" "b60205" "Data loss, security breach, or complete outage"
create_or_update "severity:high"     "d93f0b" "Major feature broken; significant user impact"
create_or_update "severity:medium"   "fbca04" "Partial degradation; workaround exists"
create_or_update "severity:low"      "c5def5" "Cosmetic; minor inconvenience"

echo "==> status"
create_or_update "status:needs-triage" "bfd4f2" "Awaiting initial review and label assignment"
create_or_update "status:blocked"      "5319e7" "Waiting on external dependency or decision"

echo "==> area"
create_or_update "area:frontend" "1d76db" "Vite + React workspace UI"
create_or_update "area:backend"  "0e8a16" "Python/FastAPI HAM backend + orchestration"
create_or_update "area:desktop"  "5319e7" "Electron shell + local-control sidecar"
create_or_update "area:ci"       "bfdadc" "Workflows, dependabot, secrets, releases"
create_or_update "area:docs"     "0075ca" "Markdown / runbooks / AGENTS.md"

echo "==> type"
create_or_update "type:bug"       "d73a4a" "Something is broken or behaving incorrectly"
create_or_update "type:feature"   "a2eeef" "New capability or enhancement"
create_or_update "type:agent-run" "1f77b4" "Cursor/Hermes agent mission run, output, or escalation"

echo "==> operational"
create_or_update "dependencies"   "0366d6" "Dependency bumps (Dependabot/Renovate)"

echo ""
echo "Done. View labels with: gh label list ${REPO_FLAG[*]:-}"
