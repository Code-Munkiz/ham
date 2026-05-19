/**
 * Phase 2 — Builder Plan approval + in-flight card (Subsystems 5–7).
 * PR 4: proposed-state UI. PR 5: in-flight progress + cancel UX.
 */
import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { Plan, PlanApprovalState, SSEEvent } from "@/lib/ham/builderPlan";
import { useJobStream } from "@/lib/ham/useJobStream";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

import {
  buildStepStatuses,
  cancelStatusLine,
  deriveCancelUiState,
  deriveInflightPhase,
  frozenSummaryLine,
  shouldShowStalledCancelWarning,
  stepStatusGlyph,
  type PlanCardInflightPhase,
} from "./planCardInflight";

export type PlanCardPhase =
  | "proposed"
  | "approved_waiting"
  | "in_flight"
  | "frozen"
  | "stale"
  | "superseded";

export type PlanCardProps = {
  plan: Plan;
  approvalState: PlanApprovalState;
  phase: PlanCardPhase;
  className?: string;
  busyBanner?: string | null;
  staleBanner?: string | null;
  approving?: boolean;
  jobId?: string | null;
  /** Overrides useJobStream for unit tests. */
  testStreamEvents?: SSEEvent[];
  onApprove?: () => void | Promise<void>;
  onReplan?: (request: string) => void;
  onCancelJob?: () => void | Promise<void>;
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
  jobId = null,
  testStreamEvents,
  onApprove,
  onReplan,
  onCancelJob,
}: PlanCardProps) {
  const [expanded, setExpanded] = React.useState(false);
  const [replanOpen, setReplanOpen] = React.useState(false);
  const [replanText, setReplanText] = React.useState("");
  const [cancelClicked, setCancelClicked] = React.useState(false);
  const [cancelClickedAtMs, setCancelClickedAtMs] = React.useState<number | null>(null);
  const [nowMs, setNowMs] = React.useState(() => Date.now());

  const useStream =
    Boolean(jobId) &&
    testStreamEvents === undefined &&
    phase !== "proposed" &&
    phase !== "stale" &&
    phase !== "superseded";

  const hookStream = useJobStream(useStream ? jobId : null);
  const streamEvents = testStreamEvents ?? hookStream.events;

  React.useEffect(() => {
    if (!cancelClicked || cancelClickedAtMs === null) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [cancelClicked, cancelClickedAtMs]);

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

  const inflightBase: PlanCardInflightPhase =
    phase === "in_flight" || phase === "frozen" ? phase : "approved_waiting";

  const resolvedPhase =
    phase === "proposed" || phase === "stale"
      ? phase
      : deriveInflightPhase(inflightBase, streamEvents);

  const stale = resolvedPhase === "stale" || approvalState === "stale";
  const approvedWaiting = resolvedPhase === "approved_waiting";
  const inFlight = resolvedPhase === "in_flight";
  const frozen = resolvedPhase === "frozen";

  const stepStatuses = buildStepStatuses(plan, streamEvents);
  const cancelState = deriveCancelUiState(streamEvents, cancelClicked);
  const cancelLine = cancelStatusLine(cancelState);
  const summaryFooter = frozen ? frozenSummaryLine(plan, streamEvents) : null;
  const stalledWarning =
    cancelClickedAtMs !== null &&
    shouldShowStalledCancelWarning(cancelClickedAtMs, streamEvents, nowMs);

  const showStepsExpanded = expanded || approvedWaiting || inFlight || frozen;
  const showApproveReplan = !approvedWaiting && !inFlight && !frozen;
  const showCancel =
    (inFlight || cancelState === "cancelling" || cancelState === "acknowledged") &&
    cancelState !== "hidden" &&
    cancelState !== "done";

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
            {approvedWaiting
              ? "Approved — waiting for worker…"
              : inFlight || frozen
                ? `Running plan (${plan.steps.length} step${plan.steps.length === 1 ? "" : "s"})`
                : planSummaryLine(plan)}
          </p>
          {showApproveReplan ? (
            <p className="mt-0.5 text-[11px] text-white/50">
              Review steps, then approve or re-plan.
            </p>
          ) : null}
        </div>
        {showApproveReplan ? (
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

      {showStepsExpanded ? (
        <ol className="mt-3 space-y-2 border-t border-white/10 pt-3" data-testid="plan-card-steps">
          {plan.steps.map((step, index) => (
            <li key={step.step_id} className="text-[12px] leading-snug">
              <div className="flex flex-wrap items-center gap-2">
                {inFlight || frozen ? (
                  <span
                    className="w-4 text-center text-white/70"
                    data-testid={`plan-card-step-status-${index}`}
                    aria-hidden
                  >
                    {stepStatusGlyph(stepStatuses[index] ?? "pending")}
                  </span>
                ) : (
                  <span className="text-white/45">{index + 1}.</span>
                )}
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

      {cancelLine ? (
        <p className="mt-2 text-[11px] text-white/65" data-testid="plan-card-cancel-status">
          {cancelLine}
        </p>
      ) : null}

      {stalledWarning ? (
        <p
          className="mt-2 text-[11px] text-amber-200/90"
          data-testid="plan-card-cancel-stalled-warning"
        >
          Cancellation taking longer than expected; the janitor will force-terminate
        </p>
      ) : null}

      {summaryFooter ? (
        <p
          className="mt-2 border-t border-white/10 pt-2 text-[11px] text-white/70"
          data-testid="plan-card-frozen-summary"
        >
          {summaryFooter}
        </p>
      ) : null}

      {showApproveReplan ? (
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

      {showCancel ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="border-white/20 bg-transparent text-white hover:bg-white/10"
            data-testid="plan-card-cancel"
            disabled={cancelState === "cancelling" || cancelState === "acknowledged"}
            onClick={() => {
              setCancelClicked(true);
              setCancelClickedAtMs(Date.now());
              void onCancelJob?.();
            }}
          >
            {cancelState === "cancelling" || cancelState === "acknowledged"
              ? "Cancelling…"
              : "Cancel"}
          </Button>
        </div>
      ) : null}

      {replanOpen && showApproveReplan ? (
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
