"""Tests for src/ham/network_egress_allowlist.py — Phase 1 #6 (ADR-0006).

Covers: allowlist constants, host matching, deny error, singleton, YAML
generation round-trip, in-sync check, and integration with the pod manifest.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from src.ham.builder_error_codes import PREVIEW_NETWORK_EGRESS_DENIED
from src.ham.builder_plan import ErrorEnvelope
from src.ham.gcp_preview_worker_manifest import build_gke_preview_pod_manifest
from src.ham.network_egress_allowlist import (
    ALLOWED_HOSTS,
    DNS_PORT,
    EGRESS_POLICY_LABEL_KEY,
    EGRESS_POLICY_LABEL_VALUE,
    EgressAllowlist,
    EgressAllowlistProtocol,
    _LLM_PROVIDER_GUARD,
    generate_yaml,
    get_egress_allowlist,
    set_egress_allowlist_for_tests,
)

# ---------------------------------------------------------------------------
# Allowlist constants
# ---------------------------------------------------------------------------


class TestAllowlistConstants:
    def test_allowed_hosts_contains_npm(self):
        assert "registry.npmjs.org" in ALLOWED_HOSTS

    def test_allowed_hosts_contains_pypi(self):
        assert "pypi.org" in ALLOWED_HOSTS

    def test_allowed_hosts_contains_pythonhosted(self):
        assert "files.pythonhosted.org" in ALLOWED_HOSTS

    def test_allowed_hosts_contains_googleapis_wildcard(self):
        assert "*.googleapis.com" in ALLOWED_HOSTS

    def test_dns_port_is_53(self):
        assert DNS_PORT == 53

    def test_no_llm_provider_hosts_in_allowlist(self):
        """ADR-0006 architectural guard: LLM providers must not appear."""
        lower = {h.lower() for h in ALLOWED_HOSTS}
        for llm_host in _LLM_PROVIDER_GUARD:
            assert llm_host.lower() not in lower, (
                f"LLM provider {llm_host!r} must not be in ALLOWED_HOSTS"
            )


# ---------------------------------------------------------------------------
# EgressAllowlist.is_host_allowed
# ---------------------------------------------------------------------------


class TestIsHostAllowed:
    def setup_method(self):
        self.al = EgressAllowlist()

    def test_npm_registry_allowed(self):
        assert self.al.is_host_allowed("registry.npmjs.org")

    def test_pypi_allowed(self):
        assert self.al.is_host_allowed("pypi.org")

    def test_pythonhosted_allowed(self):
        assert self.al.is_host_allowed("files.pythonhosted.org")

    def test_googleapis_subdomain_allowed(self):
        assert self.al.is_host_allowed("storage.googleapis.com")
        assert self.al.is_host_allowed("firestore.googleapis.com")
        assert self.al.is_host_allowed("run.googleapis.com")

    def test_googleapis_base_domain_allowed(self):
        assert self.al.is_host_allowed("googleapis.com")

    def test_case_insensitive_npm(self):
        assert self.al.is_host_allowed("Registry.npmjs.org")

    def test_case_insensitive_pypi(self):
        assert self.al.is_host_allowed("PYPI.ORG")

    def test_llm_provider_anthropic_denied(self):
        assert not self.al.is_host_allowed("api.anthropic.com")

    def test_llm_provider_openai_denied(self):
        assert not self.al.is_host_allowed("api.openai.com")

    def test_llm_provider_openrouter_denied(self):
        assert not self.al.is_host_allowed("openrouter.ai")

    def test_arbitrary_host_denied(self):
        assert not self.al.is_host_allowed("evil.example.com")

    def test_ip_address_denied(self):
        assert not self.al.is_host_allowed("10.0.0.1")

    def test_typosquat_suffix_denied(self):
        assert not self.al.is_host_allowed("evil-googleapis.com")

    def test_subdomain_injection_denied(self):
        assert not self.al.is_host_allowed("evil.googleapis.com.attacker.net")


# ---------------------------------------------------------------------------
# EgressAllowlist.deny_error
# ---------------------------------------------------------------------------


class TestDenyError:
    def setup_method(self):
        self.al = EgressAllowlist()

    def test_returns_error_envelope(self):
        err = self.al.deny_error("evil.example.com")
        assert isinstance(err, ErrorEnvelope)

    def test_error_code_is_preview_network_egress_denied(self):
        err = self.al.deny_error("evil.example.com")
        assert err.error_code == PREVIEW_NETWORK_EGRESS_DENIED

    def test_error_details_include_blocked_host(self):
        err = self.al.deny_error("evil.example.com")
        assert err.error_details is not None
        assert err.error_details["blocked_host"] == "evil.example.com"

    def test_fatal_true(self):
        err = self.al.deny_error("evil.example.com")
        assert err.fatal is True

    def test_retriable_false(self):
        err = self.al.deny_error("evil.example.com")
        assert err.retriable is False

    def test_occurred_at_set(self):
        err = self.al.deny_error("evil.example.com")
        assert err.occurred_at is not None
        assert err.occurred_at.endswith("Z")


# ---------------------------------------------------------------------------
# Protocol + singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_returns_protocol_impl(self):
        impl = get_egress_allowlist()
        assert isinstance(impl, EgressAllowlistProtocol)

    def test_same_instance_returned_twice(self):
        assert get_egress_allowlist() is get_egress_allowlist()

    def test_set_for_tests_overrides_singleton(self):
        class _FakeAllowlist:
            def is_host_allowed(self, host: str) -> bool:
                return True

            def deny_error(self, host: str) -> ErrorEnvelope:
                raise NotImplementedError

        set_egress_allowlist_for_tests(_FakeAllowlist())
        try:
            assert get_egress_allowlist().is_host_allowed("evil.example.com")
        finally:
            set_egress_allowlist_for_tests(None)

    def test_reset_to_none_restores_default(self):
        set_egress_allowlist_for_tests(None)
        assert not get_egress_allowlist().is_host_allowed("evil.example.com")


# ---------------------------------------------------------------------------
# generate_yaml round-trip
# ---------------------------------------------------------------------------


class TestGenerateYaml:
    def _doc(self) -> dict:
        return yaml.safe_load(generate_yaml())

    def test_roundtrips_through_yaml_parser(self):
        doc = yaml.safe_load(generate_yaml())
        assert doc is not None
        assert isinstance(doc, dict)

    def test_kind_is_network_policy(self):
        assert self._doc()["kind"] == "NetworkPolicy"

    def test_api_version(self):
        assert self._doc()["apiVersion"] == "networking.k8s.io/v1"

    def test_policy_types_includes_egress(self):
        assert "Egress" in self._doc()["spec"]["policyTypes"]

    def test_pod_selector_carries_egress_label(self):
        labels = self._doc()["spec"]["podSelector"]["matchLabels"]
        assert labels[EGRESS_POLICY_LABEL_KEY] == EGRESS_POLICY_LABEL_VALUE

    def test_contains_all_allowlist_entries(self):
        fqdns_str: str = self._doc()["metadata"]["annotations"]["ham.dev/allowed-fqdns"]
        for host in ALLOWED_HOSTS:
            assert host in fqdns_str, (
                f"Expected {host!r} in ham.dev/allowed-fqdns annotation"
            )

    def test_exactly_allowlist_entries_in_annotation(self):
        fqdns_str: str = self._doc()["metadata"]["annotations"]["ham.dev/allowed-fqdns"]
        entries = [e.strip() for e in fqdns_str.strip().splitlines() if e.strip()]
        assert sorted(entries) == sorted(ALLOWED_HOSTS), (
            "ham.dev/allowed-fqdns entries must match ALLOWED_HOSTS exactly"
        )

    def test_no_llm_provider_in_yaml(self):
        text = generate_yaml()
        for llm_host in _LLM_PROVIDER_GUARD:
            assert llm_host not in text, (
                f"LLM provider {llm_host!r} must not appear in generated YAML"
            )

    def test_dns_port_present_in_egress_rules(self):
        all_ports = [
            p.get("port")
            for rule in self._doc()["spec"].get("egress", [])
            for p in rule.get("ports", [])
        ]
        assert DNS_PORT in all_ports

    def test_allowlist_source_annotation(self):
        annotations = self._doc()["metadata"]["annotations"]
        assert annotations["ham.dev/allowlist-source"] == "src/ham/network_egress_allowlist.py"

    def test_custom_namespace(self):
        doc = yaml.safe_load(generate_yaml(namespace="custom-ns"))
        assert doc["metadata"]["namespace"] == "custom-ns"


# ---------------------------------------------------------------------------
# Checked-in YAML stays in sync with generate_yaml()
# ---------------------------------------------------------------------------


class TestCheckedInYamlSync:
    _YAML_PATH = pathlib.Path("infra/gcp/preview-runtime/networkpolicy-preview.yaml")

    def test_file_exists(self):
        assert self._YAML_PATH.exists(), (
            f"{self._YAML_PATH} not found; run generate_yaml() and save it"
        )

    def test_in_sync_with_generate_yaml(self):
        on_disk = self._YAML_PATH.read_text(encoding="utf-8")
        generated = generate_yaml()
        assert on_disk == generated, (
            f"{self._YAML_PATH} is out of sync with generate_yaml(). "
            "Regenerate: python -c \"from src.ham.network_egress_allowlist import "
            "generate_yaml; open('infra/gcp/preview-runtime/networkpolicy-preview.yaml', 'w').write(generate_yaml())\""
        )


# ---------------------------------------------------------------------------
# Integration: preview pod manifest carries the policy-selector label
# ---------------------------------------------------------------------------


class TestManifestIntegration:
    _MANIFEST_KWARGS = dict(
        workspace_id="ws-test-abcdef12",
        project_id="pr-test-abcdef12",
        runtime_session_id="rs-test-abcdef12",
        namespace="ham-preview",
        bundle_gs_uri="gs://test-bucket/bundle.zip",
        runner_image="gcr.io/test-project/preview-runner:latest",
    )

    def test_pod_manifest_carries_egress_policy_label(self):
        manifest = build_gke_preview_pod_manifest(**self._MANIFEST_KWARGS)
        labels = manifest["metadata"]["labels"]
        assert EGRESS_POLICY_LABEL_KEY in labels, (
            f"Pod manifest missing label {EGRESS_POLICY_LABEL_KEY!r}"
        )
        assert labels[EGRESS_POLICY_LABEL_KEY] == EGRESS_POLICY_LABEL_VALUE

    def test_egress_policy_label_value(self):
        manifest = build_gke_preview_pod_manifest(**self._MANIFEST_KWARGS)
        assert manifest["metadata"]["labels"][EGRESS_POLICY_LABEL_KEY] == "preview"
