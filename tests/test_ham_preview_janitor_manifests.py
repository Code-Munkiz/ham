"""Golden tests for HAM preview janitor Kubernetes manifests (dry-run CronJob foundation)."""

from __future__ import annotations

from pathlib import Path

import yaml

_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "gke"
    / "staging"
    / "ham-preview-janitor"
    / "cronjob-dryrun.yaml"
)


def _load_docs() -> list[dict]:
    raw = _MANIFEST.read_text(encoding="utf-8")
    return list(yaml.safe_load_all(raw))


def test_cronjob_manifest_does_not_contain_apply_flag() -> None:
    docs = _load_docs()
    cronjobs = [d for d in docs if d and d.get("kind") == "CronJob"]
    assert len(cronjobs) == 1
    cj = cronjobs[0]
    containers = (
        cj.get("spec", {})
        .get("jobTemplate", {})
        .get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    assert containers, "CronJob must define containers"
    combined = "\n".join(
        str(x)
        for co in containers
        for x in (co.get("args") or []) + (co.get("command") or [])
    )
    assert "--apply" not in combined, "Default CronJob must not pass --apply"


def test_rbac_is_namespace_scoped_role_read_only() -> None:
    docs = _load_docs()
    kinds = [d.get("kind") for d in docs if d]
    assert "ClusterRole" not in kinds
    assert "ClusterRoleBinding" not in kinds

    roles = [d for d in docs if d and d.get("kind") == "Role"]
    assert len(roles) == 1
    role = roles[0]
    assert role["metadata"]["namespace"] == "ham-builder-preview-spike"

    allowed_verbs = {"get", "list", "watch"}
    allowed_resources = {"pods", "services", "endpoints"}
    for rule in role.get("rules") or []:
        for verb in rule.get("verbs") or []:
            assert verb in allowed_verbs, f"unexpected verb {verb!r}"
        for res in rule.get("resources") or []:
            assert res in allowed_resources, f"unexpected resource {res!r}"


def test_serviceaccount_and_rolebinding_in_preview_namespace() -> None:
    docs = _load_docs()
    for d in docs:
        if not d:
            continue
        md = d.get("metadata") or {}
        if d.get("kind") in {"ServiceAccount", "RoleBinding"}:
            assert md.get("namespace") == "ham-builder-preview-spike"
