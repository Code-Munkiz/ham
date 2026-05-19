import * as React from "react";

import type { Plan, PlanApprovalRecord } from "@/lib/ham/builderPlan";
import {
  BuilderPlanApiError,
  approveBuilderPlan,
  fetchBuilderPlan,
} from "@/lib/ham/builderPlanApi";

import { PlanCard, type PlanCardPhase } from "./PlanCard";

export type BuilderPlanCardEntry = {
  planId: string;
  plan: Plan | null;
  approval: PlanApprovalRecord | null;
  phase: PlanCardPhase;
  busyBanner: string | null;
  jobId: string | null;
  loadError: string | null;
};

type WorkspaceBuilderPlanCardsProps = {
  entries: BuilderPlanCardEntry[];
  onEntriesChange: (next: BuilderPlanCardEntry[]) => void;
  onReplanMessage: (text: string) => void;
};

export function createEmptyBuilderPlanEntry(planId: string): BuilderPlanCardEntry {
  return {
    planId,
    plan: null,
    approval: null,
    phase: "proposed",
    busyBanner: null,
    jobId: null,
    loadError: null,
  };
}

export async function loadBuilderPlanEntry(planId: string): Promise<BuilderPlanCardEntry> {
  try {
    const detail = await fetchBuilderPlan(planId);
    const phase: PlanCardPhase =
      detail.approval.state === "stale"
        ? "stale"
        : detail.approval.state === "approved"
          ? "approved_waiting"
          : "proposed";
    return {
      planId,
      plan: detail.plan,
      approval: detail.approval,
      phase,
      busyBanner: null,
      jobId: null,
      loadError: null,
    };
  } catch (err) {
    return {
      ...createEmptyBuilderPlanEntry(planId),
      loadError: err instanceof Error ? err.message : "Failed to load plan",
    };
  }
}

export function WorkspaceBuilderPlanCards({
  entries,
  onEntriesChange,
  onReplanMessage,
}: WorkspaceBuilderPlanCardsProps) {
  const [approvingPlanId, setApprovingPlanId] = React.useState<string | null>(null);
  if (!entries.length) return null;

  const patchEntry = (planId: string, patch: Partial<BuilderPlanCardEntry>) => {
    onEntriesChange(entries.map((e) => (e.planId === planId ? { ...e, ...patch } : e)));
  };

  return (
    <div
      className="mx-auto w-full max-w-3xl space-y-3 py-3"
      data-testid="workspace-builder-plan-cards"
    >
      {entries.map((entry) => {
        if (entry.loadError) {
          return (
            <p
              key={entry.planId}
              className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-100"
              data-testid="plan-card-load-error"
            >
              {entry.loadError}
            </p>
          );
        }
        if (!entry.plan || !entry.approval) {
          return (
            <p key={entry.planId} className="text-[12px] text-white/50">
              Loading plan…
            </p>
          );
        }
        return (
          <PlanCard
            key={entry.planId}
            plan={entry.plan}
            approvalState={entry.approval.state}
            phase={entry.phase}
            busyBanner={entry.busyBanner}
            approving={approvingPlanId === entry.planId}
            onApprove={async () => {
              setApprovingPlanId(entry.planId);
              patchEntry(entry.planId, { busyBanner: null });
              try {
                const result = await approveBuilderPlan(entry.planId);
                patchEntry(entry.planId, {
                  phase: "approved_waiting",
                  approval: {
                    ...entry.approval!,
                    state: "approved",
                    approved_at: new Date().toISOString(),
                  },
                  jobId: result.job_id,
                  busyBanner: null,
                });
              } catch (err) {
                if (err instanceof BuilderPlanApiError && err.code === "project_busy") {
                  patchEntry(entry.planId, {
                    busyBanner: "Another build is running for this project; cancel it first",
                  });
                  return;
                }
                if (err instanceof BuilderPlanApiError && err.code === "plan_stale") {
                  patchEntry(entry.planId, {
                    phase: "stale",
                    approval: { ...entry.approval!, state: "stale" },
                  });
                  return;
                }
                patchEntry(entry.planId, {
                  busyBanner: err instanceof Error ? err.message : "Approve failed",
                });
              } finally {
                setApprovingPlanId(null);
              }
            }}
            onReplan={(text) => onReplanMessage(text)}
          />
        );
      })}
    </div>
  );
}
