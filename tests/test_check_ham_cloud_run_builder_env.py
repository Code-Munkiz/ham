from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_module():
    module_path = Path("scripts/check_ham_cloud_run_builder_env.py").resolve()
    spec = importlib.util.spec_from_file_location(
        "check_ham_cloud_run_builder_env", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load check_ham_cloud_run_builder_env module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_env_map_ignores_secret_mount_entries() -> None:
    module = _load_module()
    payload = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "env": [
                                {"name": "HAM_BUILDER_GCP_RUNTIME_ENABLED", "value": "true"},
                                {
                                    "name": "CURSOR_API_KEY",
                                    "valueFrom": {"secretKeyRef": {"name": "cursor"}},
                                },
                            ]
                        }
                    ]
                }
            }
        }
    }

    env_map = module.extract_env_map(payload)
    assert env_map == {"HAM_BUILDER_GCP_RUNTIME_ENABLED": "true"}


def test_evaluate_env_reports_missing_and_mismatch() -> None:
    module = _load_module()
    failures = module.evaluate_env(
        actual_env={
            "HAM_BUILDER_GCP_RUNTIME_ENABLED": "false",
            "HAM_BUILDER_GCP_REGION": "us-central1",
        },
        expected_env={
            "HAM_BUILDER_GCP_RUNTIME_ENABLED": "true",
            "HAM_BUILDER_GCP_REGION": "us-central1",
            "CLERK_JWT_ISSUER": "https://sharing-gobbler-70.clerk.accounts.dev",
        },
    )

    assert len(failures) == 2
    assert failures[0].key == "HAM_BUILDER_GCP_RUNTIME_ENABLED"
    assert failures[0].actual == "false"
    assert failures[1].key == "CLERK_JWT_ISSUER"
    assert failures[1].actual is None
