"""Tests for src/ham/builder_error_codes.py — error catalog + make_error().

Covers: constant completeness, make_error() round-trip, catalog size lock,
required fatal kwarg.
"""

from __future__ import annotations

import pytest

from src.ham.builder_error_codes import (
    ALL_CODES,
    GATE_ENQUEUE_FAILED,
    GATE_PLAN_STALE,
    GATE_PROJECT_BUSY,
    INTERNAL_ERROR,
    PREVIEW_NETWORK_EGRESS_DENIED,
    PREVIEW_PACKAGE_INSTALL_DENIED,
    PREVIEW_POD_CRASHED,
    PREVIEW_POD_UNSCHEDULABLE,
    STEP_FAILED,
    STEP_MODEL_UNAVAILABLE,
    STEP_TIMEOUT,
    STEP_TOOL_CALL_FAILED,
    WORKER_DISPATCH_FAILED,
    WORKER_OOM,
    WORKER_TIMEOUT,
    make_error,
)
from src.ham.builder_plan import ErrorEnvelope


# ---------------------------------------------------------------------------
# Every constant matches its documented dotted-string value
# ---------------------------------------------------------------------------


class TestCatalogConstants:
    def test_gate_plan_stale(self):
        assert GATE_PLAN_STALE == "gate.plan_stale"

    def test_gate_project_busy(self):
        assert GATE_PROJECT_BUSY == "gate.project_busy"

    def test_gate_enqueue_failed(self):
        assert GATE_ENQUEUE_FAILED == "gate.enqueue_failed"

    def test_worker_dispatch_failed(self):
        assert WORKER_DISPATCH_FAILED == "worker.worker_dispatch_failed"

    def test_worker_timeout(self):
        assert WORKER_TIMEOUT == "worker.worker_timeout"

    def test_worker_oom(self):
        assert WORKER_OOM == "worker.worker_oom"

    def test_step_failed(self):
        assert STEP_FAILED == "step.step_failed"

    def test_step_timeout(self):
        assert STEP_TIMEOUT == "step.step_timeout"

    def test_step_tool_call_failed(self):
        assert STEP_TOOL_CALL_FAILED == "step.tool_call_failed"

    def test_step_model_unavailable(self):
        assert STEP_MODEL_UNAVAILABLE == "step.model_unavailable"

    def test_preview_pod_crashed(self):
        assert PREVIEW_POD_CRASHED == "preview.preview_pod_crashed"

    def test_preview_pod_unschedulable(self):
        assert PREVIEW_POD_UNSCHEDULABLE == "preview.preview_pod_unschedulable"

    def test_preview_network_egress_denied(self):
        assert PREVIEW_NETWORK_EGRESS_DENIED == "preview.network_egress_denied"

    def test_preview_package_install_denied(self):
        assert PREVIEW_PACKAGE_INSTALL_DENIED == "preview.package_install_denied"

    def test_internal_error(self):
        assert INTERNAL_ERROR == "internal_error"


# ---------------------------------------------------------------------------
# ALL_CODES locks the v1 catalog size
# ---------------------------------------------------------------------------


class TestAllCodes:
    def test_catalog_size(self):
        assert len(ALL_CODES) == 15

    def test_every_constant_in_all_codes(self):
        expected = {
            GATE_PLAN_STALE, GATE_PROJECT_BUSY, GATE_ENQUEUE_FAILED,
            WORKER_DISPATCH_FAILED, WORKER_TIMEOUT, WORKER_OOM,
            STEP_FAILED, STEP_TIMEOUT, STEP_TOOL_CALL_FAILED, STEP_MODEL_UNAVAILABLE,
            PREVIEW_POD_CRASHED, PREVIEW_POD_UNSCHEDULABLE,
            PREVIEW_NETWORK_EGRESS_DENIED, PREVIEW_PACKAGE_INSTALL_DENIED,
            INTERNAL_ERROR,
        }
        assert ALL_CODES == expected


# ---------------------------------------------------------------------------
# make_error() produces a valid ErrorEnvelope
# ---------------------------------------------------------------------------


class TestMakeError:
    def test_produces_error_envelope(self):
        err = make_error(INTERNAL_ERROR, "boom", fatal=True)
        assert isinstance(err, ErrorEnvelope)

    def test_round_trips_through_json(self):
        err = make_error(GATE_PLAN_STALE, "Snapshot drifted", fatal=True, retriable=False)
        restored = ErrorEnvelope.model_validate_json(err.model_dump_json())
        assert restored.error_code == GATE_PLAN_STALE
        assert restored.error_message == "Snapshot drifted"
        assert restored.fatal is True
        assert restored.retriable is False

    def test_with_details(self):
        err = make_error(
            GATE_PLAN_STALE,
            "drift",
            fatal=True,
            details={"original_snapshot_id": "s1", "current_snapshot_id": "s2"},
        )
        assert err.error_details == {"original_snapshot_id": "s1", "current_snapshot_id": "s2"}

    def test_sets_occurred_at(self):
        err = make_error(INTERNAL_ERROR, "x", fatal=False)
        assert err.occurred_at is not None
        assert err.occurred_at.endswith("Z")

    def test_retriable_default_false(self):
        err = make_error(INTERNAL_ERROR, "x", fatal=False)
        assert err.retriable is False

    def test_retriable_can_be_set(self):
        err = make_error(WORKER_TIMEOUT, "timed out", fatal=True, retriable=True)
        assert err.retriable is True


# ---------------------------------------------------------------------------
# make_error() rejects missing fatal kwarg
# ---------------------------------------------------------------------------


class TestMakeErrorRequiresFatal:
    def test_missing_fatal_raises(self):
        with pytest.raises(TypeError):
            make_error(INTERNAL_ERROR, "boom")  # type: ignore[call-arg]
