import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Plan } from "@/lib/ham/builderPlan";
import { PlanCard } from "../PlanCard";

function samplePlan(overrides: Partial<Plan> = {}): Plan {
  return {
    plan_id: "pln_test",
    version: "1.0.0",
    workspace_id: "ws_test",
    project_id: "proj_test",
    source_snapshot_id: "ssnp_a",
    user_message: "add login",
    steps: [
      {
        step_id: "stp_1",
        title: "Add login form",
        description: "Landing page form",
        requires_approval: true,
      },
      {
        step_id: "stp_2",
        title: "Wire auth API",
        description: "POST /api/auth",
        requires_approval: false,
      },
    ],
    destructive: true,
    planner_model: null,
    planner_confidence: "high",
    created_at: "2026-05-19T00:00:00Z",
    metadata: {},
    ...overrides,
  };
}

describe("PlanCard", () => {
  it("renders step list and destructive badge when expanded", () => {
    render(
      <PlanCard plan={samplePlan()} approvalState="proposed" phase="proposed" />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Expand steps" }));
    expect(screen.getByTestId("plan-card-steps")).toBeInTheDocument();
    expect(screen.getAllByTestId("plan-card-destructive-badge")).toHaveLength(1);
  });

  it("calls approve handler when Approve is clicked", async () => {
    const onApprove = vi.fn();
    render(
      <PlanCard
        plan={samplePlan()}
        approvalState="proposed"
        phase="proposed"
        onApprove={onApprove}
      />,
    );
    fireEvent.click(screen.getByTestId("plan-card-approve"));
    await waitFor(() => expect(onApprove).toHaveBeenCalledTimes(1));
  });

  it("shows STALE banner and disables Approve in stale phase", () => {
    render(
      <PlanCard plan={samplePlan()} approvalState="stale" phase="stale" />,
    );
    expect(screen.getByTestId("plan-card-stale-banner")).toBeInTheDocument();
    expect(screen.getByTestId("plan-card-approve")).toBeDisabled();
  });

  it("renders superseded one-line summary", () => {
    render(
      <PlanCard plan={samplePlan()} approvalState="proposed" phase="superseded" />,
    );
    expect(screen.getByTestId("plan-card-superseded")).toHaveTextContent(/Superseded plan/i);
  });

  it("submits replan text via onReplan", () => {
    const onReplan = vi.fn();
    render(
      <PlanCard
        plan={samplePlan()}
        approvalState="proposed"
        phase="proposed"
        onReplan={onReplan}
      />,
    );
    fireEvent.click(screen.getByTestId("plan-card-replan"));
    fireEvent.change(screen.getByLabelText(/What should I change/i), {
      target: { value: "Use OAuth instead" },
    });
    fireEvent.click(screen.getByTestId("plan-card-replan-submit"));
    expect(onReplan).toHaveBeenCalledWith("Use OAuth instead");
  });
});
