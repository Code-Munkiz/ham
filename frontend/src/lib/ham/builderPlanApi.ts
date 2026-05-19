import { hamApiFetch } from "@/lib/ham/api";
import type { Plan, PlanApprovalRecord } from "@/lib/ham/builderPlan";

export type BuilderPlanDetailResponse = {
  plan: Plan;
  approval: PlanApprovalRecord;
};

export class BuilderPlanApiError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "BuilderPlanApiError";
    this.code = code;
  }
}

export async function fetchBuilderPlan(planId: string): Promise<BuilderPlanDetailResponse> {
  const res = await hamApiFetch(`/api/plans/${encodeURIComponent(planId)}`);
  if (!res.ok) {
    throw new BuilderPlanApiError("plan_not_found", `Plan fetch failed (${res.status})`);
  }
  return (await res.json()) as BuilderPlanDetailResponse;
}

export async function approveBuilderPlan(planId: string): Promise<{
  plan_id: string;
  job_id: string;
  approval_state: string;
}> {
  const res = await hamApiFetch(`/api/plans/${encodeURIComponent(planId)}/approve`, {
    method: "POST",
  });
  if (!res.ok) {
    let code = `http_${res.status}`;
    let message = `Approve failed (${res.status})`;
    try {
      const payload = (await res.json()) as {
        detail?: { error?: { code?: string; message?: string } };
      };
      code = payload.detail?.error?.code ?? code;
      message = payload.detail?.error?.message ?? message;
    } catch {
      /* ignore parse errors */
    }
    throw new BuilderPlanApiError(code, message);
  }
  return (await res.json()) as { plan_id: string; job_id: string; approval_state: string };
}
