#!/usr/bin/env bash
# Verify Hermes CLI packaging in a built ham-api Docker image (Native Builder workspace lane).
# Usage: ./scripts/verify_hermes_cli_image.sh [image-tag]
# Example: docker build -t ham-hermes-workspace-smoke . && ./scripts/verify_hermes_cli_image.sh
set -euo pipefail

IMAGE="${1:-ham-hermes-workspace-smoke}"

echo "==> Hermes CLI smoke: ${IMAGE}"

docker run --rm "${IMAGE}" sh -lc 'command -v hermes && hermes --version'

docker run --rm "${IMAGE}" python -c "
from src.ham.hermes_runtime_inventory import resolve_hermes_cli_binary
path = resolve_hermes_cli_binary()
assert path, 'resolve_hermes_cli_binary() returned None'
print('resolve_hermes_cli_binary:', path)
"

echo "==> Hermes CLI smoke passed"
