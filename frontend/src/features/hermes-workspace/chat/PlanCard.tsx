/**
 * Phase 2 — Builder Plan approval card (Subsystem 5).
 * PR 4: proposed-state UI only. PR 5+ extend in-place for in-flight / errors.
 */
import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { Plan, PlanApprovalState } from "@/lib/ham/builderPlan";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export type PlanCardPhase = "proposed" | "approved_waiting" | "stale" | "superseded";

export type PlanCardProps = {
  plan: Plan;
  approvalState: PlanApprovalState;
  phase: PlanCardPhase;
  className?: string;
  busyBanner?: string | null;
  staleBanner?: string | null;
  approving?: boolean;
  onApprove?: () => void | Promise<void>;
  onReplan?: (request: string) => void;
};

function planSummaryLine(plan: Plan): string {
  const n = plan.steps.length;
  const stepWord = n === 1 ? "step" : "steps";
  const touch = plan.destructive ? "touches sensitive paths" : "scoped changes";
  return `Plan: ${n} ${stepWord}; ${touch}`;
}

export function PlanCard({
  plan,
  approvalState,
  phase,
  className,
  busyBanner,
  staleBanner,
  approving = false,
  onApprove,
  onReplan,
}: PlanCardProps) {
  const [expanded, setExpanded] = React.useState(false);
  const [replanOpen, setReplanOpen] = React.useState(false);
  const [replanText, setReplanText] = React.useState("");

  if (phase === "superseded") {
    return (
      <div
        className={cn(
          "rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[12px] text-white/55",
          className,
        )}
        data-testid="plan-card-superseded"
      >
        Superseded plan ({plan.steps.length} step{plan.steps.length === 1 ? "" : "s"})
      </div>
    );
  }

  const stale = phase === "stale" || approvalState === "stale";
  const approvedWaiting = phase === "approved_waiting" || approvalState === "approved";

  return (
    <div
      className={cn(
        "rounded-xl border border-white/[0.12] bg-white/[0.04] p-3 text-white/90 shadow-sm",
        stale && "opacity-70",
        className,
      )}
      data-testid="plan-card"
      data-plan-id={plan.plan_id}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[13px] font-medium text-white/95" data-testid="plan-card-summary">
            {approvedWaiting ? "Approved — waiting for worker…" : planSummaryLine(plan)}
          </p>
          {!approvedWaiting ? (
            <p className="mt-0.5 text-[11px] text-white/50">
              Review steps, then approve or re-plan.
            </p>
          ) : null}
        </div>
        {!approvedWaiting ? (
          <button
            type="button"
            className="mt-0.5 text-white/60 hover:text-white/90"
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse steps" : "Expand steps"}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        ) : null}
      </div>

      {busyBanner ? (
        <p
          className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-100"
          data-testid="plan-card-busy-banner"
        >
          {busyBanner}
        </p>
      ) : null}

      {staleBanner || stale ? (
        <p
          className="mt-2 rounded-md border border-white/15 bg-white/[0.06] px-2 py-1.5 text-[11px] text-white/70"
          data-testid="plan-card-stale-banner"
        >
          {staleBanner ?? "Project changed since this plan was created; ask me again"}
        </p>
      ) : null}

      {expanded && !approvedWaiting ? (
        <ol className="mt-3 space-y-2 border-t border-white/10 pt-3" data-testid="plan-card-steps">
          {plan.steps.map((step, index) => (
            <li key={step.step_id} className="text-[12px] leading-snug">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-white/45">{index + 1}.</span>
                <span className="font-medium text-white/90">{step.title}</span>
                {step.requires_approval ? (
                  <span
                    className="rounded-full border border-red-400/40 bg-red-500/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-red-200"
                    data-testid="plan-card-destructive-badge"
                  >
                    Destructive
                  </span>
                ) : null}
              </div>
              {step.description ? (
                <p className="mt-0.5 pl-5 text-[11px] text-white/55">{step.description}</p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      {!approvedWaiting ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            disabled={stale || approving || Boolean(busyBanner)}
            data-testid="plan-card-approve"
            onClick={() => void onApprove?.()}
          >
            {approving ? "Approving…" : "Approve"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="border-white/20 bg-transparent text-white hover:bg-white/10"
            data-testid="plan-card-replan"
            onClick={() => setReplanOpen((v) => !v)}
          >
            Re-plan
          </Button>
        </div>
      ) : null}

      {replanOpen && !approvedWaiting ? (
        <div
          className="mt-3 space-y-2 border-t border-white/10 pt-3"
          data-testid="plan-card-replan-prompt"
        >
          <label className="text-[11px] text-white/60" htmlFor={`replan-${plan.plan_id}`}>
            What should I change?
          </label>
          <textarea
            id={`replan-${plan.plan_id}`}
            className="min-h-[72px] w-full rounded-md border border-white/15 bg-black/30 px-2 py-1.5 text-[12px] text-white"
            value={replanText}
            onChange={(e) => setReplanText(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={!replanText.trim()}
            data-testid="plan-card-replan-submit"
            onClick={() => {
              const text = replanText.trim();
              if (!text) return;
              onReplan?.(text);
              setReplanText("");
              setReplanOpen(false);
            }}
          >
            Send re-plan message
          </Button>
        </div>
      ) : null}
    </div>
  );
}
