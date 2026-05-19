import { describe, expect, it } from "vitest";

import type { Plan, SSEEvent } from "@/lib/ham/builderPlan";

import {
  buildStepErrors,
  buildStepStatuses,
  deriveCancelUiState,
  deriveInflightPhase,
  extractJobFailedError,
  frozenSummaryLine,
  shouldShowStalledCancelWarning,
} from "../planCardInflight";

function samplePlan(): Plan {
  return {
    plan_id: "pln_test",
    version: "1.0.0",
    workspace_id: "ws",
    project_id: "proj",
    source_snapshot_id: null,
    user_message: "x",
    steps: [
      {
        step_id: "stp_1",
        title: "One",
        description: "",
        requires_approval: false,
      },
      {
        step_id: "stp_2",
        title: "Two",
        description: "",
        requires_approval: false,
      },
    ],
    destructive: false,
    planner_model: null,
    planner_confidence: "high",
    created_at: "2026-05-19T00:00:00Z",
    metadata: {},
  };
}

function ev(type: SSEEvent["event"]["type"], extra: Record<string, unknown> = {}): SSEEvent {
  return {
    version: "1.0.0",
    seq: 1,
    job_id: "crjb_1",
    plan_id: "pln_test",
    occurred_at: "2026-05-19T00:00:00Z",
    event: { type, ...extra } as SSEEvent["event"],
  };
}

describe("planCardInflight", () => {
  it("derives in_flight after job_started", () => {
    const phase = deriveInflightPhase("approved_waiting", [ev("job_started")]);
    expect(phase).toBe("in_flight");
  });

  it("builds step status transitions", () => {
    const plan = samplePlan();
    const events = [
      ev("step_started", { step_id: "stp_1", step_index: 0, title: "One" }),
      ev("step_completed", { step_id: "stp_1", step_index: 0 }),
      ev("step_started", { step_id: "stp_2", step_index: 1, title: "Two" }),
    ];
    expect(buildStepStatuses(plan, events)).toEqual(["completed", "running"]);
  });

  it("cancel UI moves through cancelling and acknowledged", () => {
    expect(deriveCancelUiState([ev("job_started")], false)).toBe("idle");
    expect(deriveCancelUiState([ev("job_started")], true)).toBe("cancelling");
    expect(deriveCancelUiState([ev("job_started"), ev("cancel_acknowledged")], true)).toBe(
      "acknowledged",
    );
    expect(
      deriveCancelUiState(
        [
          ev("job_started"),
          ev("cancel_acknowledged"),
          ev("job_cancelled", { cancelled_at_step_id: "stp_2" }),
        ],
        true,
      ),
    ).toBe("done");
  });

  it("frozen cancel summary mentions applied steps", () => {
    const plan = samplePlan();
    const summary = frozenSummaryLine(plan, [
      ev("job_cancelled", { cancelled_at_step_id: "stp_2" }),
    ]);
    expect(summary).toMatch(/Cancelled after Step 2 of 2/);
    expect(summary).toMatch(/Step 1/);
  });

  it("maps runtime_error to most recent step", () => {
    const plan = samplePlan();
    const errors = buildStepErrors(plan, [
      ev("step_started", { step_id: "stp_1", step_index: 0, title: "One" }),
      ev("step_completed", { step_id: "stp_1", step_index: 0 }),
      ev("step_started", { step_id: "stp_2", step_index: 1, title: "Two" }),
      {
        ...ev("runtime_error"),
        event: {
          type: "runtime_error",
          error: {
            version: "1.0.0",
            error_code: "worker.internal_error",
            error_message: "boom",
            error_details: null,
            retriable: false,
            fatal: true,
            occurred_at: "2026-05-19T00:00:00Z",
          },
        },
      },
    ]);
    expect(errors[1]?.error_message).toBe("boom");
  });

  it("extracts job_failed error envelope", () => {
    const err = extractJobFailedError([
      {
        ...ev("job_failed"),
        event: {
          type: "job_failed",
          error: {
            version: "1.0.0",
            error_code: "step.step_failed",
            error_message: "done",
            error_details: null,
            retriable: false,
            fatal: true,
            occurred_at: "2026-05-19T00:00:00Z",
          },
        },
      },
    ]);
    expect(err?.error_message).toBe("done");
  });

  it("shows 30s stalled cancel warning", () => {
    const now = 100_000;
    expect(shouldShowStalledCancelWarning(now - 31_000, [ev("job_started")], now)).toBe(true);
    expect(shouldShowStalledCancelWarning(now - 5_000, [ev("job_started")], now)).toBe(false);
    expect(
      shouldShowStalledCancelWarning(
        now - 60_000,
        [ev("job_cancelled", { cancelled_at_step_id: null })],
        now,
      ),
    ).toBe(false);
  });
});
