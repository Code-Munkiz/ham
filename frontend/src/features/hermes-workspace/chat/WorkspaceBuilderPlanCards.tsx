import * as React from "react";

import type { ErrorEnvelope, Plan, PlanApprovalRecord } from "@/lib/ham/builderPlan";
import {
  BuilderPlanApiError,
  approveBuilderPlan,
  fetchBuilderPlan,
} from "@/lib/ham/builderPlanApi";
import { BuilderJobApiError, cancelBuilderJob } from "@/lib/ham/builderJobApi";

import { PlanCard, type PlanCardPhase } from "./PlanCard";
import { PlanJobFailureAssistant } from "./PlanJobFailureAssistant";

export type BuilderPlanCardEntry = {
  planId: string;
  plan: Plan | null;
  approval: PlanApprovalRecord | null;
  phase: PlanCardPhase;
  busyBanner: string | null;
  jobId: string | null;
  loadError: string | null;
  jobFailedError: ErrorEnvelope | null;
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
    jobFailedError: null,
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
      jobFailedError: null,
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
  const [forceReplanPlanId, setForceReplanPlanId] = React.useState<string | null>(null);
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
          <React.Fragment key={entry.planId}>
            <PlanCard
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
              jobId={entry.jobId}
              onReplan={(text) => onReplanMessage(text)}
              onCancelJob={
                entry.jobId
                  ? async () => {
                      try {
                        await cancelBuilderJob(entry.jobId!);
                      } catch (err) {
                        if (
                          err instanceof BuilderJobApiError &&
                          err.code === "job_already_terminal"
                        ) {
                          return;
                        }
                        patchEntry(entry.planId, {
                          busyBanner: err instanceof Error ? err.message : "Cancel failed",
                        });
                      }
                    }
                  : undefined
              }
              forceReplanOpen={forceReplanPlanId === entry.planId}
              onJobFailed={(error) => patchEntry(entry.planId, { jobFailedError: error })}
            />
            {entry.jobFailedError ? (
              <PlanJobFailureAssistant
                error={entry.jobFailedError}
                onTryAgain={() => onReplanMessage(entry.plan!.user_message)}
                onEditReplan={() => setForceReplanPlanId(entry.planId)}
              />
            ) : null}
          </React.Fragment>
        );
      })}
    </div>
  );
}
