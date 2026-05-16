from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict


EXPECTED_ENV: dict[str, str] = {
    "HAM_BUILDER_CLOUD_RUNTIME_PROVIDER": "gcp_gke_sandbox",
    "HAM_BUILDER_CLOUD_RUNTIME_EXPERIMENTS_ENABLED": "true",
    "HAM_BUILDER_GCP_RUNTIME_ENABLED": "true",
    "HAM_BUILDER_GCP_RUNTIME_DRY_RUN": "false",
    "HAM_BUILDER_GCP_RUNTIME_LIVE_K8S_ENABLED": "true",
    "HAM_BUILDER_GCP_RUNTIME_LIVE_BUNDLE_UPLOAD": "true",
    "HAM_BUILDER_PREVIEW_PROXY_AUTH_DIAGNOSTICS": "1",
    "HAM_BUILDER_GCP_PROJECT_ID": "clarity-staging-488201",
    "HAM_BUILDER_GCP_REGION": "us-central1",
    "HAM_BUILDER_GKE_CLUSTER": "ham-preview-spike",
    "HAM_BUILDER_GKE_NAMESPACE_PREFIX": "ham-builder-preview",
    "HAM_BUILDER_PREVIEW_SOURCE_BUCKET": "ham-preview-sources-clarity-staging-488201",
    "HAM_BUILDER_PREVIEW_RUNNER_IMAGE": "us-central1-docker.pkg.dev/clarity-staging-488201/ham/ham-preview-runner:main-3ba2ac73",
    "HAM_CLERK_REQUIRE_AUTH": "true",
    "CLERK_JWT_ISSUER": "https://sharing-gobbler-70.clerk.accounts.dev",
}


@dataclass(frozen=True)
class EnvCheckFailure:
    key: str
    expected: str
    actual: str | None


def extract_env_map(service_payload: dict) -> Dict[str, str]:
    """Extract plain env vars from a Cloud Run service JSON payload."""
    containers = (
        service_payload.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    if not containers:
        return {}
    env_entries = containers[0].get("env", [])
    env_map: dict[str, str] = {}
    for entry in env_entries:
        key = entry.get("name")
        if not key:
            continue
        # Secret-mounted entries typically use valueFrom; this script checks
        # only explicit non-secret env values.
        if "value" in entry:
            env_map[key] = str(entry["value"])
    return env_map


def evaluate_env(actual_env: Dict[str, str], expected_env: Dict[str, str]) -> list[EnvCheckFailure]:
    failures: list[EnvCheckFailure] = []
    for key, expected_value in expected_env.items():
        actual_value = actual_env.get(key)
        if actual_value != expected_value:
            failures.append(
                EnvCheckFailure(key=key, expected=expected_value, actual=actual_value)
            )
    return failures


def fetch_service_payload(project: str, region: str, service: str) -> dict:
    command = [
        "gcloud",
        "run",
        "services",
        "describe",
        service,
        "--project",
        project,
        "--region",
        region,
        "--format=json",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gcloud CLI is not installed or not on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"gcloud describe failed: {stderr or exc}") from exc

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Unable to parse gcloud JSON output.") from exc


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Cloud Run ham-api builder/auth env drift (read-only)."
    )
    parser.add_argument(
        "--project",
        default="clarity-staging-488201",
        help="GCP project id (default: clarity-staging-488201)",
    )
    parser.add_argument(
        "--region",
        default="us-central1",
        help="Cloud Run region (default: us-central1)",
    )
    parser.add_argument(
        "--service",
        default="ham-api",
        help="Cloud Run service name (default: ham-api)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        service_payload = fetch_service_payload(
            project=args.project,
            region=args.region,
            service=args.service,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    actual_env = extract_env_map(service_payload)
    failures = evaluate_env(actual_env=actual_env, expected_env=EXPECTED_ENV)

    print(
        f"Checked {len(EXPECTED_ENV)} non-secret env vars "
        f"for {args.service} ({args.project}/{args.region})."
    )
    if not failures:
        print("PASS: builder/auth runtime env matches expected values.")
        return 0

    print("FAIL: env drift detected.")
    for failure in failures:
        actual = "<missing>" if failure.actual is None else failure.actual
        print(f"- {failure.key}: expected='{failure.expected}' actual='{actual}'")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
