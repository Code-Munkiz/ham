"""NetworkPolicy egress allowlist for preview pods — Phase 1 #6 (ADR-0006).

Python is the source of truth for allowed hosts. ``generate_yaml()`` emits the
NetworkPolicy YAML checked in at infra/gcp/preview-runtime/networkpolicy-preview.yaml.
Do not hand-edit the YAML; regenerate it from this module.

Spec: docs/adr/0006-preview-pod-egress-deny-default.md
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import yaml  # pyyaml>=6.0 in requirements.txt

from src.ham.builder_error_codes import PREVIEW_NETWORK_EGRESS_DENIED, make_error
from src.ham.builder_plan import ErrorEnvelope

# ---------------------------------------------------------------------------
# Allowlist constants — source of truth per ADR-0006
# ---------------------------------------------------------------------------

DNS_PORT: int = 53

ALLOWED_HOSTS: tuple[str, ...] = (
    "registry.npmjs.org",
    "pypi.org",
    "files.pythonhosted.org",
    "*.googleapis.com",
)

# Intentionally excluded per ADR-0006: the Worker calls LLMs; preview pods do not.
_LLM_PROVIDER_GUARD: frozenset[str] = frozenset(
    {
        "api.anthropic.com",
        "api.openai.com",
        "openrouter.ai",
        "api.hermes.gateway",
    }
)

# Label applied to preview pods so the NetworkPolicy podSelector picks them up.
EGRESS_POLICY_LABEL_KEY: str = "ham.egress-policy"
EGRESS_POLICY_LABEL_VALUE: str = "preview"

# ---------------------------------------------------------------------------
# Protocol + singleton (mirrors builder_runtime_job_store pattern)
# ---------------------------------------------------------------------------

_POLICY_NAME = "ham-preview-egress-policy"
_DEFAULT_NAMESPACE = "ham-preview"
_ALLOWLIST_SOURCE = "src/ham/network_egress_allowlist.py"
_ADR_REF = "docs/adr/0006-preview-pod-egress-deny-default.md"


@runtime_checkable
class EgressAllowlistProtocol(Protocol):
    def is_host_allowed(self, host: str) -> bool: ...
    def deny_error(self, host: str) -> ErrorEnvelope: ...


class EgressAllowlist:
    """Evaluates whether a host is in the curated egress allowlist."""

    def is_host_allowed(self, host: str) -> bool:
        """Return True if host matches an entry in ALLOWED_HOSTS."""
        h = host.strip().lower()
        for pattern in ALLOWED_HOSTS:
            if pattern.startswith("*."):
                suffix = "." + pattern[2:]  # "*.googleapis.com" -> ".googleapis.com"
                if h == pattern[2:] or h.endswith(suffix):
                    return True
            elif h == pattern.lower():
                return True
        return False

    def deny_error(self, host: str) -> ErrorEnvelope:
        """Return a fatal ErrorEnvelope for a blocked egress attempt."""
        return make_error(
            PREVIEW_NETWORK_EGRESS_DENIED,
            f"Egress to {host!r} is denied by the preview pod allowlist.",
            fatal=True,
            retriable=False,
            details={"blocked_host": host},
        )


_SINGLETON: list[EgressAllowlistProtocol | None] = [None]


def get_egress_allowlist() -> EgressAllowlistProtocol:
    if _SINGLETON[0] is None:
        _SINGLETON[0] = EgressAllowlist()
    return _SINGLETON[0]


def set_egress_allowlist_for_tests(impl: EgressAllowlistProtocol | None) -> None:
    _SINGLETON[0] = impl


# ---------------------------------------------------------------------------
# YAML generation
# ---------------------------------------------------------------------------


def generate_yaml(*, namespace: str = _DEFAULT_NAMESPACE) -> str:
    """Emit the deny-default NetworkPolicy YAML for preview pods.

    FQDN-based filtering requires Calico or Cilium FQDN policy support on
    the cluster. This standard K8s NetworkPolicy provides the deny-default
    baseline (policyTypes: [Egress]); the ham.dev/allowed-fqdns annotation
    is the machine-readable source of truth for the FQDN layer.
    """
    doc = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": _POLICY_NAME,
            "namespace": namespace,
            "annotations": {
                "ham.dev/allowlist-source": _ALLOWLIST_SOURCE,
                "ham.dev/adr": _ADR_REF,
                "ham.dev/allowed-fqdns": "\n".join(ALLOWED_HOSTS),
            },
        },
        "spec": {
            "podSelector": {
                "matchLabels": {
                    EGRESS_POLICY_LABEL_KEY: EGRESS_POLICY_LABEL_VALUE,
                }
            },
            "policyTypes": ["Egress"],
            "egress": [
                {
                    # DNS: kube-dns — required for hostname resolution
                    "ports": [
                        {"protocol": "UDP", "port": DNS_PORT},
                        {"protocol": "TCP", "port": DNS_PORT},
                    ],
                },
                {
                    # HTTPS: curated allowlist (FQDN enforcement via Calico/Cilium)
                    "to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}],
                    "ports": [{"protocol": "TCP", "port": 443}],
                },
            ],
        },
    }
    header = (
        "# Generated by src/ham/network_egress_allowlist.py"
        " \u2014 do not edit by hand.\n"
        "# Regenerate: python -c \"from src.ham.network_egress_allowlist"
        " import generate_yaml; print(generate_yaml())\"\n"
        f"# See {_ADR_REF}\n"
    )
    return header + yaml.dump(doc, default_flow_style=False, sort_keys=False)
