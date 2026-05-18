from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.ham.gcp_preview_runtime_client import FakeGkePreviewRuntimeClient
from src.ham.preview_janitor import (
    PreviewJanitorConfig,
    apply_janitor_plan,
    build_age_bucket_counts,
    build_janitor_plan,
    check_preview_concurrency_violation,
    concurrency_cap_excess_pods,
    count_active_preview_pods_by_scope,
    derive_companion_service_name,
    get_preview_concurrency_cap_config,
    janitor_plan_to_report_dict,
    load_kubernetes_list_json,
    parse_endpoints_ready_count,
    select_expired_pod_candidates,
)
from scripts.ham_preview_janitor import main as janitor_main


def _now() -> datetime:
    return datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)


def _pod(
    *,
    name: str,
    ns: str = "ham-builder-preview-spike",
    created: datetime | None = None,
    expires: str | None = None,
    app: str = "ham-builder-preview",
    session: str = "rtms-test",
    workspace: str = "ws-test",
    phase: str = "Running",
) -> dict:
    created = created or _now()
    ts = created.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "kind": "Pod",
        "metadata": {
            "name": name,
            "namespace": ns,
            "creationTimestamp": ts,
            "labels": {
                "app.kubernetes.io/name": app,
                "ham.runtime_session_id": session,
                "ham.workspace_id": workspace,
                "ham.project_id": "proj",
                "ham.preview_ttl_seconds": "3600",
                "ham.expires_at": expires or "",
            },
        },
        "status": {"phase": phase},
    }


def test_expired_by_ham_expires_at_selected() -> None:
    now = _now()
    past = (now - timedelta(hours=3)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    expires_label = past.replace(":", "-")
    pod = _pod(name="ham-preview-rtms-dead", created=now - timedelta(hours=4), expires=expires_label)
    cfg = PreviewJanitorConfig(grace_seconds=600, max_lifetime_seconds=86400)
    cands = select_expired_pod_candidates(pod_items=[pod], now=now, config=cfg)
    assert len(cands) == 1
    assert "expires_at_with_grace" in cands[0].reasons


def test_expired_by_max_lifetime_selected() -> None:
    now = _now()
    future = (now + timedelta(hours=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    expires_label = future.replace(":", "-")
    pod = _pod(name="ham-preview-rtms-old", created=now - timedelta(hours=30), expires=expires_label)
    cfg = PreviewJanitorConfig(grace_seconds=600, max_lifetime_seconds=86400)
    cands = select_expired_pod_candidates(pod_items=[pod], now=now, config=cfg)
    assert len(cands) == 1
    assert "max_lifetime_exceeded" in cands[0].reasons


def test_fresh_pod_not_selected() -> None:
    now = _now()
    future = (now + timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    expires_label = future.replace(":", "-")
    pod = _pod(name="ham-preview-rtms-fresh", created=now - timedelta(minutes=10), expires=expires_label)
    cfg = PreviewJanitorConfig(grace_seconds=600, max_lifetime_seconds=86400)
    cands = select_expired_pod_candidates(pod_items=[pod], now=now, config=cfg)
    assert len(cands) == 0


def test_foreign_labels_not_selected() -> None:
    now = _now()
    past = (now - timedelta(hours=3)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    pod = _pod(
        name="other",
        app="some-other-app",
        expires=past.replace(":", "-"),
        created=now - timedelta(hours=4),
    )
    cfg = PreviewJanitorConfig()
    cands = select_expired_pod_candidates(pod_items=[pod], now=now, config=cfg)
    assert len(cands) == 0


def test_companion_service_of_expired_pod_in_plan() -> None:
    now = _now()
    past = (now - timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    name = "ham-preview-rtms-xyz"
    pod = _pod(name=name, created=now - timedelta(hours=3), expires=past.replace(":", "-"))
    plan = build_janitor_plan(pod_items=[pod], service_items=None, now=now, config=PreviewJanitorConfig())
    assert len(plan.pod_candidates) == 1
    assert len(plan.service_candidates) == 1
    assert plan.service_candidates[0].service_name == derive_companion_service_name(name)
    assert "companion_of_expired_pod" in plan.service_candidates[0].reasons


def test_orphan_ham_preview_service_zero_endpoints() -> None:
    now = _now()
    future = (now + timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    alive = _pod(
        name="ham-preview-rtms-alive",
        session="rtms-alive",
        created=now - timedelta(minutes=30),
        expires=future.replace(":", "-"),
    )
    svc = {
        "kind": "Service",
        "metadata": {
            "name": "orphan-svc",
            "namespace": "ham-builder-preview-spike",
            "labels": {
                "app.kubernetes.io/name": "ham-builder-preview",
                "ham.runtime_session_id": "rtms-orphan",
                "ham.workspace_id": "ws-o",
                "ham.project_id": "proj",
            },
        },
    }
    eps = [{"kind": "Endpoints", "metadata": {"namespace": "ham-builder-preview-spike", "name": "orphan-svc"}}]
    plan = build_janitor_plan(
        pod_items=[alive],
        service_items=[svc],
        endpoint_ready_counts=parse_endpoints_ready_count(eps),
        now=now,
        config=PreviewJanitorConfig(),
    )
    orphan = [s for s in plan.service_candidates if "orphan_no_ready_endpoints" in s.reasons]
    assert len(orphan) == 1
    assert orphan[0].service_name == "orphan-svc"


def test_orphan_not_selected_without_ham_labels() -> None:
    now = _now()
    alive = _pod(name="ham-preview-rtms-alive", created=now - timedelta(minutes=5), session="s1")
    future = (now + timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    alive["metadata"]["labels"]["ham.expires_at"] = future.replace(":", "-")
    svc = {
        "kind": "Service",
        "metadata": {
            "name": "plain-svc",
            "namespace": "ham-builder-preview-spike",
            "labels": {"app": "other"},
        },
    }
    eps = [{"kind": "Endpoints", "metadata": {"namespace": "ham-builder-preview-spike", "name": "plain-svc"}}]
    plan = build_janitor_plan(
        pod_items=[alive],
        service_items=[svc],
        endpoint_ready_counts=parse_endpoints_ready_count(eps),
        now=now,
    )
    orphan = [s for s in plan.service_candidates if "orphan_no_ready_endpoints" in s.reasons]
    assert orphan == []


def test_report_default_dry_run_not_apply() -> None:
    now = _now()
    past = (now - timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    pod = _pod(name="p1", session="s1", created=now - timedelta(hours=3), expires=past.replace(":", "-"))
    plan = build_janitor_plan(pod_items=[pod], now=now)
    report = janitor_plan_to_report_dict(plan, mode="dry_run", apply_flag_passed=False)
    assert report["dry_run"] is True
    assert report["apply_flag_passed"] is False


def test_apply_requires_explicit_flag_on_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pods = {
        "kind": "List",
        "items": [
            _pod(
                name="pflag",
                session="sflag",
                created=_now() - timedelta(hours=4),
                expires=(_now() - timedelta(hours=3)).replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
                .replace(":", "-"),
            )
        ],
    }
    path = Path(__file__).resolve().parent / "_janitor_pods_tmp.json"
    path.write_text(json.dumps(pods), encoding="utf-8")
    try:
        mock_client = MagicMock()
        mock_client.delete_preview_pod.return_value = True
        mock_client.delete_preview_service.return_value = True
        monkeypatch.setattr(
            "scripts.ham_preview_janitor.build_gke_runtime_client",
            lambda: mock_client,
        )
        rc = janitor_main(["--pods-json", str(path)])
        assert rc == 0
        mock_client.delete_preview_pod.assert_not_called()
        mock_client.delete_preview_service.assert_not_called()
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["destructive_apply_executed"] is False
        assert payload.get("apply_flag_passed") is False

        rc2 = janitor_main(["--pods-json", str(path), "--apply"])
        assert rc2 == 0
        assert mock_client.delete_preview_pod.call_count >= 1
        assert mock_client.delete_preview_service.call_count >= 1
        out2 = capsys.readouterr().out
        payload2 = json.loads(out2)
        assert payload2["destructive_apply_executed"] is True
        assert payload2["apply_flag_passed"] is True
    finally:
        path.unlink(missing_ok=True)


def test_age_buckets_match_expected() -> None:
    now = _now()
    pods = [
        _pod(name="a", created=now - timedelta(minutes=30), session="s1"),
        _pod(name="b", created=now - timedelta(hours=3), session="s2"),
        _pod(name="c", created=now - timedelta(hours=10), session="s3"),
        _pod(name="d", created=now - timedelta(hours=30), session="s4"),
    ]
    future = (now + timedelta(hours=5)).isoformat().replace("+00:00", "Z").replace(":", "-")
    for p in pods:
        p["metadata"]["labels"]["ham.expires_at"] = future
    buckets = build_age_bucket_counts(pods, now=now)
    assert buckets["lt_1h"] == 1
    assert buckets["h1_6"] == 1
    assert buckets["h6_24"] == 1
    assert buckets["gt_24h"] == 1


def test_concurrency_cap_returns_excess_without_delete() -> None:
    now = _now()
    base = now - timedelta(hours=5)
    pods = []
    for i in range(4):
        created = base + timedelta(minutes=i * 15)
        pods.append(_pod(name=f"ham-preview-rtms-cap-{i}", session="rtms-same", workspace="ws-x", created=created))
    future = (now + timedelta(hours=5)).isoformat().replace("+00:00", "Z").replace(":", "-")
    for p in pods:
        p["metadata"]["labels"]["ham.expires_at"] = future.replace(":", "-")

    out = concurrency_cap_excess_pods(
        pod_items=pods,
        now=now,
        session_cap=3,
        workspace_cap=10,
    )
    assert out["over_session_cap_count"] == 1
    assert out["over_workspace_cap_count"] == 0


def test_apply_janitor_plan_deletes_with_fake_client() -> None:
    now = _now()
    past = (now - timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    client = FakeGkePreviewRuntimeClient(mode="success")
    pod_manifest = _pod(
        name="ham-preview-rtms-wipe",
        created=now - timedelta(hours=3),
        expires=past.replace(":", "-"),
    )
    client.create_preview_pod(manifest={"metadata": pod_manifest["metadata"], "spec": {"containers": []}})
    plan = build_janitor_plan(pod_items=[pod_manifest], now=now, config=PreviewJanitorConfig())
    counts = apply_janitor_plan(client=client, plan=plan)
    assert counts["deleted_pods"] == 1
    assert counts["deleted_services"] == 1


def test_load_kubernetes_list_json() -> None:
    raw = '{"kind":"List","items":[{"kind":"Pod","metadata":{"name":"x","namespace":"n"}}]}'
    items = load_kubernetes_list_json(raw)
    assert len(items) == 1
    assert items[0]["kind"] == "Pod"


def _labs(ws_key: str, rs_key: str, proj: str = "p1") -> dict[str, str]:
    return {
        "app.kubernetes.io/name": "ham-builder-preview",
        "ham.workspace_id": ws_key,
        "ham.runtime_session_id": rs_key,
        "ham.project_id": proj,
    }


def test_preview_concurrency_counts_pending_and_running_not_terminal() -> None:
    from src.ham.gcp_preview_worker_manifest import sanitize_dns_label

    ws_raw = "ws_alpha"
    rs_raw = "rtms_aaa"
    wk = sanitize_dns_label(ws_raw, max_len=63)
    rk = sanitize_dns_label(rs_raw, max_len=63)
    items = [
        {
            "metadata": {"name": "a", "labels": _labs(wk, rk)},
            "status": {"phase": "Pending"},
        },
        {
            "metadata": {"name": "b", "labels": _labs(wk, rk)},
            "status": {"phase": "Running"},
        },
        {
            "metadata": {"name": "c", "labels": _labs(wk, rk)},
            "status": {"phase": "Succeeded"},
        },
    ]
    s, w = count_active_preview_pods_by_scope(
        items, workspace_id_raw=ws_raw, runtime_session_id_raw=rs_raw
    )
    assert s == 2
    assert w == 2


def test_preview_concurrency_ignores_foreign_and_incomplete_labels() -> None:
    from src.ham.gcp_preview_worker_manifest import sanitize_dns_label

    ws_raw = "ws_beta"
    rs_raw = "rtms_bbb"
    wk = sanitize_dns_label(ws_raw, max_len=63)
    rk = sanitize_dns_label(rs_raw, max_len=63)
    items = [
        {
            "metadata": {
                "name": "x1",
                "labels": {**_labs(wk, rk), "app.kubernetes.io/name": "something-else"},
            },
            "status": {"phase": "Running"},
        },
        {
            "metadata": {
                "name": "x2",
                "labels": {
                    "app.kubernetes.io/name": "ham-builder-preview",
                    "ham.runtime_session_id": rk,
                },
            },
            "status": {"phase": "Running"},
        },
    ]
    s, w = count_active_preview_pods_by_scope(
        items, workspace_id_raw=ws_raw, runtime_session_id_raw=rs_raw
    )
    assert s == 0
    assert w == 0


def test_check_preview_concurrency_violation_reports_session_over_cap() -> None:
    from src.ham.gcp_preview_worker_manifest import sanitize_dns_label

    ws_raw = "ws_gamma"
    rs_raw = "rtms_ccc"
    wk = sanitize_dns_label(ws_raw, max_len=63)
    rk = sanitize_dns_label(rs_raw, max_len=63)
    triple = [
        {"metadata": {"name": f"p{i}", "labels": _labs(wk, rk)}, "status": {"phase": "Running"}}
        for i in range(3)
    ]
    msg = check_preview_concurrency_violation(
        triple,
        workspace_id_raw=ws_raw,
        runtime_session_id_raw=rs_raw,
        session_cap=3,
        workspace_cap=5,
    )
    assert msg is not None
    assert "session" in msg.lower()


def test_check_preview_concurrency_violation_reports_workspace_over_cap() -> None:
    from src.ham.gcp_preview_worker_manifest import sanitize_dns_label

    ws_raw = "ws_delta"
    wk = sanitize_dns_label(ws_raw, max_len=63)
    items = [
        {
            "metadata": {
                "name": f"w{i}",
                "labels": _labs(wk, sanitize_dns_label(f"rtms_{i}", max_len=63)),
            },
            "status": {"phase": "Running"},
        }
        for i in range(5)
    ]
    msg = check_preview_concurrency_violation(
        items,
        workspace_id_raw=ws_raw,
        runtime_session_id_raw="rtms_new",
        session_cap=3,
        workspace_cap=5,
    )
    assert msg is not None
    assert "workspace" in msg.lower()


def test_preview_concurrency_under_cap_returns_none() -> None:
    from src.ham.gcp_preview_worker_manifest import sanitize_dns_label

    ws_raw = "ws_eps"
    rs_raw = "rtms_ddd"
    wk = sanitize_dns_label(ws_raw, max_len=63)
    rk = sanitize_dns_label(rs_raw, max_len=63)
    items = [
        {"metadata": {"name": "p0", "labels": _labs(wk, rk)}, "status": {"phase": "Running"}},
    ]
    assert (
        check_preview_concurrency_violation(
            items,
            workspace_id_raw=ws_raw,
            runtime_session_id_raw=rs_raw,
            session_cap=3,
            workspace_cap=5,
        )
        is None
    )


def test_get_preview_concurrency_cap_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_PREVIEW_SESSION_CAP", raising=False)
    monkeypatch.delenv("HAM_BUILDER_PREVIEW_WORKSPACE_CAP", raising=False)
    assert get_preview_concurrency_cap_config() == (3, 5)


def test_cap_logic_does_not_invoke_client_delete() -> None:
    client = FakeGkePreviewRuntimeClient(mode="success")
    client.delete_preview_pod = MagicMock(return_value=True)  # type: ignore[method-assign]
    spy = client.delete_preview_pod
    client.seed_preview_pod_for_tests(
        namespace="ns",
        name="p1",
        labels=_labs("ws", "rs"),
        phase="Running",
    )
    client.seed_preview_pod_for_tests(
        namespace="ns",
        name="p2",
        labels=_labs("ws", "rs"),
        phase="Running",
    )
    client.seed_preview_pod_for_tests(
        namespace="ns",
        name="p3",
        labels=_labs("ws", "rs"),
        phase="Running",
    )
    items = client.list_preview_pods(namespace="ns")
    msg = check_preview_concurrency_violation(
        items,
        workspace_id_raw="ws",
        runtime_session_id_raw="rs",
        session_cap=3,
        workspace_cap=5,
    )
    assert msg is not None
    spy.assert_not_called()
