"""Verifier integration at end-of-Plan in BuilderWorker (Phase 2 #362)."""

from __future__ import annotations

import types as types_mod
from unittest.mock import patch

import pytest

from src.ham.builder_error_codes import STEP_FAILED, STEP_VERIFICATION_FAILED, make_error
from src.ham.builder_verifier import VerifierOutcome
from src.ham.builder_worker import BuilderWorker, StepResult
from tests.test_builder_worker import (
    _FakeEventsStore,
    _FakeJobStore,
    _FakePlanStore,
    _make_job,
    _make_plan,
)

_PREVIEW_URL = "https://preview.example.test"


def _make_worker_with_preview(
    job_id: str = "crjb_verify",
    *,
    plan=None,
    job=None,
) -> tuple[BuilderWorker, _FakeEventsStore, _FakeJobStore]:
    plan = plan or _make_plan()
    job = job or _make_job(job_id, plan_id=plan.plan_id)
    plan_store = _FakePlanStore(plans=[plan])
    job_store = _FakeJobStore(jobs=[job])
    events_store = _FakeEventsStore()
    worker = BuilderWorker(
        job_id,
        plan_store=plan_store,
        job_store=job_store,
        events_store=events_store,
        preview_url=_PREVIEW_URL,
    )
    return worker, events_store, job_store


class TestBuilderWorkerVerifierIntegration:
    @patch("src.ham.builder_worker.verify")
    def test_verifier_pass_emits_job_completed(self, mock_verify):
        mock_verify.return_value = VerifierOutcome(success=True)
        worker, events_store, job_store = _make_worker_with_preview()
        worker.run()

        mock_verify.assert_called_once()
        called_plan, called_url = mock_verify.call_args[0]
        assert called_plan.plan_id == "pln_test"
        assert called_url == _PREVIEW_URL

        types = events_store.event_types("crjb_verify")
        assert "job_completed" in types
        assert "job_failed" not in types
        job = job_store.get_cloud_runtime_job_by_id(job_id="crjb_verify")
        assert job is not None
        assert job.status == "completed"

    @patch("src.ham.builder_worker.verify")
    def test_verifier_fail_emits_step_failed_then_job_failed(self, mock_verify):
        err = make_error(
            STEP_VERIFICATION_FAILED,
            "Playwright verification failed",
            fatal=True,
        )
        mock_verify.return_value = VerifierOutcome(success=False, error_envelope=err)

        plan = _make_plan()
        worker, events_store, job_store = _make_worker_with_preview(plan=plan)
        worker.run()

        types = events_store.event_types("crjb_verify")
        assert types.count("step_completed") == len(plan.steps)
        assert "step_failed" in types
        assert "job_failed" in types
        assert "job_completed" not in types

        failed = [
            e
            for e in events_store.events_for_job("crjb_verify")
            if e.event.type == "step_failed"
        ]
        assert len(failed) == 1
        assert failed[0].event.step_id == plan.steps[-1].step_id
        assert failed[0].event.error.error_code == STEP_VERIFICATION_FAILED

        job = job_store.get_cloud_runtime_job_by_id(job_id="crjb_verify")
        assert job is not None
        assert job.status == "failed"
        assert job.last_error is not None
        assert job.last_error.error_code == STEP_VERIFICATION_FAILED

    @patch("src.ham.builder_worker.verify")
    def test_prior_step_failure_skips_verifier(self, mock_verify):
        plan = _make_plan()
        job = _make_job("crjb_verify", plan_id=plan.plan_id)
        plan_store = _FakePlanStore(plans=[plan])
        job_store = _FakeJobStore(jobs=[job])
        events_store = _FakeEventsStore()
        worker = BuilderWorker(
            "crjb_verify",
            plan_store=plan_store,
            job_store=job_store,
            events_store=events_store,
            preview_url=_PREVIEW_URL,
        )

        def _fail_first(self, step, **kwargs):
            err = make_error(STEP_FAILED, "Step blew up", fatal=True)
            return StepResult(success=False, error_envelope=err)

        worker._execute_step = types_mod.MethodType(_fail_first, worker)
        worker.run()

        mock_verify.assert_not_called()
        event_types = events_store.event_types("crjb_verify")
        assert "step_failed" in event_types
        assert "job_failed" in event_types
        assert "job_completed" not in event_types

    @patch("src.ham.builder_worker.verify")
    def test_no_preview_url_skips_verifier(self, mock_verify):
        plan = _make_plan()
        job = _make_job("crjb_verify", plan_id=plan.plan_id)
        worker = BuilderWorker(
            "crjb_verify",
            plan_store=_FakePlanStore(plans=[plan]),
            job_store=_FakeJobStore(jobs=[job]),
            events_store=_FakeEventsStore(),
            preview_url="",
        )
        worker.run()
        mock_verify.assert_not_called()
