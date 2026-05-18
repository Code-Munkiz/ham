#!/usr/bin/env python3
"""HAM Builder GKE preview janitor — **dry-run by default** (JSON report to stdout).

Reads Kubernetes List JSON (e.g. from ``kubectl get … -o json``). Never contacts the
cluster unless ``--apply`` is passed (still requires a configured GKE client).

Examples (read-only gather + plan):

  kubectl get pods -n NAMESPACE -l app.kubernetes.io/name=ham-builder-preview -o json \\
    | python scripts/ham_preview_janitor.py --pods-json -

  python scripts/ham_preview_janitor.py --pods-json pods.json \\
    --services-json svc.json --endpoints-json ep.json

**Do not pass ``--apply`` until review + approval.**
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.ham.gcp_preview_runtime_client import build_gke_runtime_client
from src.ham.preview_janitor import (
    PreviewJanitorConfig,
    apply_janitor_plan,
    build_janitor_plan,
    janitor_plan_to_report_dict,
    load_kubernetes_list_json,
    parse_endpoints_ready_count,
)


def _read_arg_path(path: str) -> str:
    if path in {"-", ""}:
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pods-json",
        required=True,
        help="Path to Pod List JSON, or '-' for stdin",
    )
    parser.add_argument(
        "--services-json",
        default="",
        help="Optional Service List JSON for orphan detection",
    )
    parser.add_argument(
        "--endpoints-json",
        default="",
        help="Optional Endpoints List JSON (same namespaces as services)",
    )
    parser.add_argument("--grace-seconds", type=int, default=600)
    parser.add_argument("--max-lifetime-hours", type=int, default=24)
    parser.add_argument("--session-cap", type=int, default=3)
    parser.add_argument("--workspace-cap", type=int, default=5)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Destructive: delete planned Pods/Services via GKE runtime client. Default off.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    pod_raw = _read_arg_path(args.pods_json)
    pod_items = load_kubernetes_list_json(pod_raw)
    svc_items: list[dict] | None = None
    ep_counts = None
    if str(args.services_json or "").strip():
        svc_items = load_kubernetes_list_json(_read_arg_path(str(args.services_json)))
        if str(args.endpoints_json or "").strip():
            ep_items = load_kubernetes_list_json(_read_arg_path(str(args.endpoints_json)))
            ep_counts = parse_endpoints_ready_count(ep_items)

    cfg = PreviewJanitorConfig(
        grace_seconds=max(0, int(args.grace_seconds)),
        max_lifetime_seconds=max(0, int(args.max_lifetime_hours) * 3600),
        session_cap=max(1, int(args.session_cap)),
        workspace_cap=max(1, int(args.workspace_cap)),
    )
    plan = build_janitor_plan(
        pod_items=pod_items,
        service_items=svc_items,
        endpoint_ready_counts=ep_counts,
        config=cfg,
    )

    apply_flag = bool(args.apply)
    report = janitor_plan_to_report_dict(plan, mode="dry_run", apply_flag_passed=apply_flag)
    report["destructive_apply_executed"] = False

    if apply_flag:
        client = build_gke_runtime_client()
        counts = apply_janitor_plan(client=client, plan=plan)
        report["destructive_apply_executed"] = True
        report["mode"] = "apply_executed"
        report["dry_run"] = False
        report["apply_delete_counts"] = counts
    else:
        report["apply_delete_counts"] = None

    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
