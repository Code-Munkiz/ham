#!/usr/bin/env python3
"""Emit a YAML Pod manifest for the GCP preview spike (does not apply to the cluster).

Outputs Kubernetes YAML suitable for manual ``kubectl apply -f`` during spikes only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.ham.gcp_preview_worker_manifest import build_gke_preview_pod_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Render GKE preview Pod manifest (stdout YAML).")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--runtime-session-id", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--bundle-uri", required=True, help="gs://… URI for uploaded preview-source.zip")
    parser.add_argument("--runner-image", required=True)
    parser.add_argument("--preview-port", type=int, default=3000)
    parser.add_argument("--ttl-seconds", type=int, default=3600)
    args = parser.parse_args()

    manifest = build_gke_preview_pod_manifest(
        workspace_id=args.workspace_id,
        project_id=args.project_id,
        runtime_session_id=args.runtime_session_id,
        namespace=args.namespace,
        bundle_gs_uri=args.bundle_uri,
        runner_image=args.runner_image,
        preview_port=args.preview_port,
        ttl_seconds=args.ttl_seconds,
    )
    sys.stdout.write(yaml.safe_dump(manifest, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
