"""HAM Builder GKE preview cost-control: pure selection + dry-run janitor foundation.

No cluster I/O here — callers pass Kubernetes List API objects (Pods/Services) as dicts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from src.ham.gcp_preview_runtime_client import (
    GkePreviewRuntimeClient,
    PreviewPodRef,
    _parse_label_expires,
)
from src.ham.gcp_preview_worker_manifest import sanitize_dns_label

# Labels set on preview Pods and companion Services by the GKE runtime client + manifest.
HAM_PREVIEW_APP_LABEL_KEY = "app.kubernetes.io/name"
HAM_PREVIEW_APP_LABEL_VALUE = "ham-builder-preview"
HAM_LABEL_RUNTIME_SESSION = "ham.runtime_session_id"
HAM_LABEL_WORKSPACE = "ham.workspace_id"
HAM_LABEL_PROJECT = "ham.project_id"
HAM_LABEL_EXPIRES_AT = "ham.expires_at"

DEFAULT_GRACE_SECONDS = 600
DEFAULT_MAX_LIFETIME_SECONDS = 24 * 3600
DEFAULT_SESSION_CAP = 3
DEFAULT_WORKSPACE_CAP = 5

AgeBucket = Literal["lt_1h", "h1_6", "h6_24", "gt_24h"]


@dataclass(frozen=True)
class PreviewJanitorConfig:
    grace_seconds: int = DEFAULT_GRACE_SECONDS
    max_lifetime_seconds: int = DEFAULT_MAX_LIFETIME_SECONDS
    session_cap: int = DEFAULT_SESSION_CAP
    workspace_cap: int = DEFAULT_WORKSPACE_CAP


@dataclass(frozen=True)
class PodExpireCandidate:
    namespace: str
    pod_name: str
    companion_service_name: str
    labels: dict[str, str]
    reasons: tuple[str, ...]
    creation_timestamp: str | None


@dataclass(frozen=True)
class ServiceExpireCandidate:
    namespace: str
    service_name: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class JanitorPlan:
    pod_candidates: tuple[PodExpireCandidate, ...]
    service_candidates: tuple[ServiceExpireCandidate, ...]  # companion + orphan, deduped
    age_buckets_pods: dict[str, int]
    reasons_breakdown: dict[str, int]
    concurrency: dict[str, Any]


def _sha12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _metadata_labels(obj: dict[str, Any]) -> dict[str, str]:
    md = obj.get("metadata") or {}
    raw = md.get("labels") or {}
    return {str(k): str(v) for k, v in raw.items()}


def _metadata_ns_name(obj: dict[str, Any]) -> tuple[str, str]:
    md = obj.get("metadata") or {}
    return str(md.get("namespace") or ""), str(md.get("name") or "")


def _parse_creation_timestamp(meta: dict[str, Any]) -> datetime | None:
    raw = str(meta.get("creationTimestamp") or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
        return datetime.fromisoformat(raw).astimezone(UTC)
    except ValueError:
        return None


def derive_companion_service_name(pod_name: str) -> str:
    """Match ``LiveGkePreviewRuntimeClient.create_preview_service`` naming."""
    base = str(pod_name or "").strip()
    return f"{base[:52]}-svc"


def is_eligible_ham_preview_pod(labels: dict[str, str]) -> bool:
    if labels.get(HAM_PREVIEW_APP_LABEL_KEY) != HAM_PREVIEW_APP_LABEL_VALUE:
        return False
    if not str(labels.get(HAM_LABEL_RUNTIME_SESSION) or "").strip():
        return False
    return True


def is_eligible_ham_preview_service(labels: dict[str, str]) -> bool:
    if labels.get(HAM_PREVIEW_APP_LABEL_KEY) != HAM_PREVIEW_APP_LABEL_VALUE:
        return False
    if not str(labels.get(HAM_LABEL_RUNTIME_SESSION) or "").strip():
        return False
    return True


# Phases that must not count toward preview concurrency (pod is finished / released).
PREVIEW_POD_TERMINAL_PHASES = frozenset({"Succeeded", "Failed"})


def preview_pod_labels_countable_for_concurrency_caps(labels: dict[str, str]) -> bool:
    """
    Stricter than janitor pod eligibility: require workspace id so caps align with manifests.
    """

    if not is_eligible_ham_preview_pod(labels):
        return False
    return bool(str(labels.get(HAM_LABEL_WORKSPACE) or "").strip())


def preview_pod_item_active_for_concurrency_caps(item: dict[str, Any]) -> bool:
    """Pending/Running (and non-terminal Unknown) count; Succeeded/Failed do not."""

    status = item.get("status") or {}
    phase = str(status.get("phase") or "").strip()
    if phase in PREVIEW_POD_TERMINAL_PHASES:
        return False
    return True


def count_active_preview_pods_by_scope(
    items: list[dict[str, Any]],
    *,
    workspace_id_raw: str,
    runtime_session_id_raw: str,
) -> tuple[int, int]:
    """
    Return (session_scoped_count, workspace_scoped_count) for active eligible preview pods.

    Label values are compared using the same DNS sanitization as ``build_gke_preview_pod_manifest``.
    """

    ws_key = sanitize_dns_label(workspace_id_raw, max_len=63)
    rs_key = sanitize_dns_label(runtime_session_id_raw, max_len=63)
    session_n = 0
    workspace_n = 0
    for item in items:
        md = item.get("metadata") or {}
        if not str(md.get("name") or "").strip():
            continue
        if not preview_pod_item_active_for_concurrency_caps(item):
            continue
        raw_labels = md.get("labels") or {}
        labels = {str(k): str(v) for k, v in raw_labels.items()}
        if not preview_pod_labels_countable_for_concurrency_caps(labels):
            continue
        if labels.get(HAM_LABEL_RUNTIME_SESSION) == rs_key:
            session_n += 1
        if labels.get(HAM_LABEL_WORKSPACE) == ws_key:
            workspace_n += 1
    return session_n, workspace_n


def get_preview_concurrency_cap_config() -> tuple[int, int]:
    """
    (session_cap, workspace_cap). Defaults match :class:`PreviewJanitorConfig`.

    Optional positive integers: ``HAM_BUILDER_PREVIEW_SESSION_CAP``,
    ``HAM_BUILDER_PREVIEW_WORKSPACE_CAP`` (no deploy required for defaults).
    """

    import os

    def _parse(name: str, default: int) -> int:
        raw = str(os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            parsed = int(raw)
            return parsed if parsed > 0 else default
        except ValueError:
            return default

    return (
        _parse("HAM_BUILDER_PREVIEW_SESSION_CAP", DEFAULT_SESSION_CAP),
        _parse("HAM_BUILDER_PREVIEW_WORKSPACE_CAP", DEFAULT_WORKSPACE_CAP),
    )


def check_preview_concurrency_violation(
    items: list[dict[str, Any]],
    *,
    workspace_id_raw: str,
    runtime_session_id_raw: str,
    session_cap: int,
    workspace_cap: int,
) -> str | None:
    """If caps are already reached, return a safe operator-facing message; else ``None``."""

    if session_cap < 1 or workspace_cap < 1:
        return None
    session_n, workspace_n = count_active_preview_pods_by_scope(
        items,
        workspace_id_raw=workspace_id_raw,
        runtime_session_id_raw=runtime_session_id_raw,
    )
    if session_n >= session_cap:
        return (
            "Too many active builder preview instances are already running for this session. "
            "Wait for an existing preview to finish or stop one, then try again."
        )
    if workspace_n >= workspace_cap:
        return (
            "Too many active builder preview instances are already running for this workspace. "
            "Wait for an existing preview to finish or stop one, then try again."
        )
    return None


def pod_expire_reasons(
    *,
    labels: dict[str, str],
    created: datetime | None,
    now: datetime,
    grace_seconds: int,
    max_lifetime_seconds: int,
) -> list[str]:
    if not is_eligible_ham_preview_pod(labels):
        return []
    reasons: list[str] = []
    expires_at = _parse_label_expires(labels.get(HAM_LABEL_EXPIRES_AT))
    if expires_at is not None:
        if now >= expires_at + timedelta(seconds=max(0, grace_seconds)):
            reasons.append("expires_at_with_grace")
    if created is not None and max_lifetime_seconds > 0:
        if (now - created).total_seconds() > max_lifetime_seconds:
            reasons.append("max_lifetime_exceeded")
    return reasons


def age_bucket_for_datetime(*, created: datetime | None, now: datetime) -> AgeBucket:
    if created is None:
        return "gt_24h"
    hours = max(0.0, (now - created).total_seconds() / 3600.0)
    if hours < 1:
        return "lt_1h"
    if hours < 6:
        return "h1_6"
    if hours < 24:
        return "h6_24"
    return "gt_24h"


def build_age_bucket_counts(pods: list[dict[str, Any]], *, now: datetime) -> dict[str, int]:
    counts: dict[str, int] = {"lt_1h": 0, "h1_6": 0, "h6_24": 0, "gt_24h": 0}
    for item in pods:
        if str(item.get("kind") or "") != "Pod":
            continue
        labels = _metadata_labels(item)
        if not is_eligible_ham_preview_pod(labels):
            continue
        meta = item.get("metadata") or {}
        created = _parse_creation_timestamp(meta)
        b = age_bucket_for_datetime(created=created, now=now)
        counts[b] += 1
    return counts


def select_expired_pod_candidates(
    *,
    pod_items: list[dict[str, Any]],
    now: datetime,
    config: PreviewJanitorConfig,
) -> tuple[PodExpireCandidate, ...]:
    out: list[PodExpireCandidate] = []
    for item in pod_items:
        if str(item.get("kind") or "") != "Pod":
            continue
        meta = item.get("metadata") or {}
        ns, name = _metadata_ns_name(item)
        labels = _metadata_labels(item)
        created = _parse_creation_timestamp(meta)
        reasons = pod_expire_reasons(
            labels=labels,
            created=created,
            now=now,
            grace_seconds=config.grace_seconds,
            max_lifetime_seconds=config.max_lifetime_seconds,
        )
        if not reasons:
            continue
        companion = derive_companion_service_name(name)
        out.append(
            PodExpireCandidate(
                namespace=ns,
                pod_name=name,
                companion_service_name=companion,
                labels=dict(labels),
                reasons=tuple(reasons),
                creation_timestamp=str(meta.get("creationTimestamp") or "") or None,
            )
        )
    return tuple(out)


def _protected_companion_service_names(
    *,
    pod_items: list[dict[str, Any]],
    expired_pod_keys: set[tuple[str, str]],
    now: datetime,
    config: PreviewJanitorConfig,
) -> set[tuple[str, str]]:
    """Companion Services still backing a *non-expired* eligible preview Pod."""
    protected: set[tuple[str, str]] = set()
    for item in pod_items:
        if str(item.get("kind") or "") != "Pod":
            continue
        meta = item.get("metadata") or {}
        ns, name = _metadata_ns_name(item)
        labels = _metadata_labels(item)
        created = _parse_creation_timestamp(meta)
        reasons = pod_expire_reasons(
            labels=labels,
            created=created,
            now=now,
            grace_seconds=config.grace_seconds,
            max_lifetime_seconds=config.max_lifetime_seconds,
        )
        if reasons:
            continue
        if not is_eligible_ham_preview_pod(labels):
            continue
        if (ns, name) in expired_pod_keys:
            continue
        companion = derive_companion_service_name(name)
        protected.add((ns, companion))
    return protected


def select_service_candidates(
    *,
    pod_items: list[dict[str, Any]],
    service_items: list[dict[str, Any]] | None,
    expired_pods: tuple[PodExpireCandidate, ...],
    endpoint_ready_counts: dict[tuple[str, str], int] | None,
    now: datetime,
    config: PreviewJanitorConfig,
) -> tuple[ServiceExpireCandidate, ...]:
    svcs: dict[tuple[str, str], ServiceExpireCandidate] = {}
    expired_keys = {(p.namespace, p.pod_name) for p in expired_pods}
    for p in expired_pods:
        key = (p.namespace, p.companion_service_name)
        if key not in svcs:
            svcs[key] = ServiceExpireCandidate(
                namespace=p.namespace,
                service_name=p.companion_service_name,
                reasons=("companion_of_expired_pod",),
            )
    if not service_items or endpoint_ready_counts is None:
        return tuple(svcs.values())

    protected = _protected_companion_service_names(
        pod_items=pod_items,
        expired_pod_keys=expired_keys,
        now=now,
        config=config,
    )

    for item in service_items:
        if str(item.get("kind") or "") != "Service":
            continue
        meta = item.get("metadata") or {}
        ns, sname = _metadata_ns_name(item)
        labels = _metadata_labels(item)
        if not is_eligible_ham_preview_service(labels):
            continue
        key = (ns, sname)
        ready = int(endpoint_ready_counts.get(key, -1))
        if ready != 0:
            continue
        if key in protected:
            continue
        reasons: tuple[str, ...]
        if any(p.companion_service_name == sname and p.namespace == ns for p in expired_pods):
            continue
        reasons = ("orphan_no_ready_endpoints",)
        if key in svcs:
            if "orphan_no_ready_endpoints" not in svcs[key].reasons:
                merged = tuple(dict.fromkeys(svcs[key].reasons + reasons))
                svcs[key] = ServiceExpireCandidate(namespace=ns, service_name=sname, reasons=merged)
        else:
            svcs[key] = ServiceExpireCandidate(namespace=ns, service_name=sname, reasons=reasons)
    return tuple(svcs.values())


def concurrency_cap_excess_pods(
    *,
    pod_items: list[dict[str, Any]],
    now: datetime,
    session_cap: int,
    workspace_cap: int,
    _phase_allow: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return oldest Pods beyond per-session / per-workspace caps (dry-run signal only)."""
    phases = _phase_allow or frozenset({"Running"})
    eligible: list[tuple[datetime, str, str, str, str]] = []
    for item in pod_items:
        if str(item.get("kind") or "") != "Pod":
            continue
        phase = str((item.get("status") or {}).get("phase") or "")
        if phase not in phases:
            continue
        meta = item.get("metadata") or {}
        ns, name = _metadata_ns_name(item)
        labels = _metadata_labels(item)
        if not is_eligible_ham_preview_pod(labels):
            continue
        created = _parse_creation_timestamp(meta) or datetime.min.replace(tzinfo=UTC)
        sess = str(labels.get(HAM_LABEL_RUNTIME_SESSION) or "")
        ws = str(labels.get(HAM_LABEL_WORKSPACE) or "")
        eligible.append((created, ns, name, sess, ws))

    def excess_for_groups(
        items: list[tuple[datetime, str, str, str]],
        cap: int,
        trim_reason: str,
    ) -> list[dict[str, Any]]:
        groups: dict[str, list[tuple[datetime, str, str]]] = {}
        for created, ns, name, key in items:
            groups.setdefault(key, []).append((created, ns, name))
        excess: list[dict[str, Any]] = []
        for gkey, rows in groups.items():
            rows_sorted = sorted(rows, key=lambda r: r[0])
            if len(rows_sorted) <= cap:
                continue
            doomed = rows_sorted[: len(rows_sorted) - cap]
            for created, ns, name in doomed:
                excess.append(
                    {
                        "pod_redacted": _sha12(f"{ns}/{name}"),
                        "namespace": ns,
                        "group": gkey[:16] + ("…" if len(gkey) > 16 else ""),
                        "would_trim_reason": trim_reason,
                        "age_seconds": int((now - created).total_seconds()),
                    }
                )
        return excess

    session_rows = [(c, ns, n, s) for c, ns, n, s, _w in eligible]
    workspace_rows = [(c, ns, n, w) for c, ns, n, _s, w in eligible if w]

    sess_excess = excess_for_groups(session_rows, max(1, session_cap), "over_session_cap")
    ws_excess = excess_for_groups(workspace_rows, max(1, workspace_cap), "over_workspace_cap")

    return {
        "session_cap": session_cap,
        "workspace_cap": workspace_cap,
        "over_session_cap_candidates": sess_excess,
        "over_workspace_cap_candidates": ws_excess,
        "over_session_cap_count": len(sess_excess),
        "over_workspace_cap_count": len(ws_excess),
    }


def build_janitor_plan(
    *,
    pod_items: list[dict[str, Any]],
    service_items: list[dict[str, Any]] | None = None,
    endpoint_ready_counts: dict[tuple[str, str], int] | None = None,
    now: datetime | None = None,
    config: PreviewJanitorConfig | None = None,
) -> JanitorPlan:
    when = now or datetime.now(UTC)
    cfg = config or PreviewJanitorConfig()
    pod_candidates = select_expired_pod_candidates(pod_items=pod_items, now=when, config=cfg)
    svc_candidates = select_service_candidates(
        pod_items=pod_items,
        service_items=service_items,
        expired_pods=pod_candidates,
        endpoint_ready_counts=endpoint_ready_counts,
        now=when,
        config=cfg,
    )
    age_all = build_age_bucket_counts(pod_items, now=when)
    rb: dict[str, int] = {}
    for p in pod_candidates:
        for r in p.reasons:
            rb[r] = rb.get(r, 0) + 1
    for s in svc_candidates:
        for r in s.reasons:
            rb[f"svc:{r}"] = rb.get(f"svc:{r}", 0) + 1

    concurrency = concurrency_cap_excess_pods(
        pod_items=pod_items,
        now=when,
        session_cap=cfg.session_cap,
        workspace_cap=cfg.workspace_cap,
    )

    return JanitorPlan(
        pod_candidates=pod_candidates,
        service_candidates=svc_candidates,
        age_buckets_pods=age_all,
        reasons_breakdown=rb,
        concurrency=concurrency,
    )


def janitor_plan_to_report_dict(
    plan: JanitorPlan,
    *,
    mode: Literal["dry_run", "apply"],
    apply_flag_passed: bool,
) -> dict[str, Any]:
    pod_payload = []
    for p in plan.pod_candidates:
        pod_payload.append(
            {
                "pod_redacted": _sha12(f"{p.namespace}/{p.pod_name}"),
                "companion_service_redacted": _sha12(f"{p.namespace}/{p.companion_service_name}"),
                "reasons": list(p.reasons),
            }
        )
    svc_payload = []
    for s in plan.service_candidates:
        svc_payload.append(
            {
                "service_redacted": _sha12(f"{s.namespace}/{s.service_name}"),
                "reasons": list(s.reasons),
            }
        )

    return {
        "mode": mode,
        "apply_flag_passed": apply_flag_passed,
        "would_delete": bool(plan.pod_candidates or plan.service_candidates),
        "dry_run": mode == "dry_run",
        "expired_pods_count": len(plan.pod_candidates),
        "expired_services_count": len(plan.service_candidates),
        "age_buckets_eligible_preview_pods": plan.age_buckets_pods,
        "reasons_breakdown": plan.reasons_breakdown,
        "pod_candidates_redacted": pod_payload,
        "service_candidates_redacted": svc_payload,
        "concurrency": plan.concurrency,
    }


def apply_janitor_plan(*, client: GkePreviewRuntimeClient, plan: JanitorPlan) -> dict[str, int]:
    """Delete Pods and companion/orphan Services. Call only after explicit operator approval."""
    deleted_pods = 0
    deleted_services = 0

    for p in plan.pod_candidates:
        ref = PreviewPodRef(
            namespace=p.namespace,
            pod_name=p.pod_name,
            service_name=None,
            labels=p.labels,
        )
        if client.delete_preview_pod(pod_ref=ref):
            deleted_pods += 1

    for s in plan.service_candidates:
        ref = PreviewPodRef(
            namespace=s.namespace,
            pod_name="_janitor_",
            service_name=s.service_name,
            labels=None,
        )
        if client.delete_preview_service(pod_ref=ref):
            deleted_services += 1

    return {"deleted_pods": deleted_pods, "deleted_services": deleted_services}


def parse_endpoints_ready_count(endpoints_items: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    """Derive ready address counts per Service from Endpoints objects (subsets[].addresses)."""
    out: dict[tuple[str, str], int] = {}
    for item in endpoints_items:
        if str(item.get("kind") or "") != "Endpoints":
            continue
        meta = item.get("metadata") or {}
        ns = str(meta.get("namespace") or "")
        name = str(meta.get("name") or "")
        subsets = item.get("subsets") or []
        n_ready = 0
        for sub in subsets:
            for addr in sub.get("addresses") or []:
                if isinstance(addr, dict):
                    n_ready += 1
        out[(ns, name)] = n_ready
    return out


def load_kubernetes_list_json(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    if isinstance(data, dict) and str(data.get("kind") or "") == "List":
        items = data.get("items") or []
        return [x for x in items if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    raise ValueError("Expected Kubernetes object or List JSON")


def report_json(plan: JanitorPlan, *, apply_flag_passed: bool) -> str:
    payload = janitor_plan_to_report_dict(
        plan,
        mode="apply" if apply_flag_passed else "dry_run",
        apply_flag_passed=apply_flag_passed,
    )
    return json.dumps(payload, indent=2, sort_keys=True)
