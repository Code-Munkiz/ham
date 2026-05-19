import type { ErrorEnvelope, Plan, SSEEvent } from "@/lib/ham/builderPlan";

export type StepRunStatus = "pending" | "running" | "completed" | "failed";

export type PlanCardInflightPhase = "approved_waiting" | "in_flight" | "frozen";

export type CancelUiState = "hidden" | "idle" | "clicking" | "cancelling" | "acknowledged" | "done";

const TERMINAL_JOB_EVENTS = new Set(["job_completed", "job_failed", "job_cancelled"]);

export function deriveInflightPhase(
  basePhase: PlanCardInflightPhase | "proposed" | "stale" | "superseded",
  events: SSEEvent[],
): PlanCardInflightPhase | "proposed" | "stale" | "superseded" {
  if (basePhase === "proposed" || basePhase === "stale" || basePhase === "superseded") {
    return basePhase;
  }
  if (events.some((e) => TERMINAL_JOB_EVENTS.has(e.event.type))) {
    return "frozen";
  }
  if (
    events.some(
      (e) =>
        e.event.type === "job_started" ||
        e.event.type === "step_started" ||
        e.event.type === "step_completed" ||
        e.event.type === "step_failed",
    )
  ) {
    return "in_flight";
  }
  return "approved_waiting";
}

export function buildStepStatuses(plan: Plan, events: SSEEvent[]): StepRunStatus[] {
  const statuses: StepRunStatus[] = plan.steps.map(() => "pending");
  for (const ev of events) {
    const payload = ev.event;
    if (payload.type === "step_started") {
      const idx = plan.steps.findIndex((s) => s.step_id === payload.step_id);
      if (idx >= 0) statuses[idx] = "running";
    }
    if (payload.type === "step_completed") {
      const idx = plan.steps.findIndex((s) => s.step_id === payload.step_id);
      if (idx >= 0) statuses[idx] = "completed";
    }
    if (payload.type === "step_failed") {
      const idx = plan.steps.findIndex((s) => s.step_id === payload.step_id);
      if (idx >= 0) statuses[idx] = "failed";
    }
  }
  return statuses;
}

export function stepStatusGlyph(status: StepRunStatus): string {
  switch (status) {
    case "pending":
      return "∘";
    case "running":
      return "▶";
    case "completed":
      return "✓";
    case "failed":
      return "✗";
  }
}

export function deriveCancelUiState(events: SSEEvent[], cancelClicked: boolean): CancelUiState {
  if (events.some((e) => e.event.type === "job_cancelled")) return "done";
  if (events.some((e) => e.event.type === "cancel_acknowledged")) return "acknowledged";
  if (cancelClicked) return "cancelling";
  const terminal = events.some((e) => TERMINAL_JOB_EVENTS.has(e.event.type));
  const started = events.some(
    (e) => e.event.type === "job_started" || e.event.type === "step_started",
  );
  if (terminal || !started) return "hidden";
  return "idle";
}

export function cancelStatusLine(cancelState: CancelUiState): string | null {
  switch (cancelState) {
    case "cancelling":
      return "Sending cancel signal…";
    case "acknowledged":
      return "Cancelling — current step finishing…";
    default:
      return null;
  }
}

export function frozenSummaryLine(plan: Plan, events: SSEEvent[]): string | null {
  const terminal = events.find((e) => TERMINAL_JOB_EVENTS.has(e.event.type));
  if (!terminal) return null;
  const n = plan.steps.length;
  const m = n === 1 ? "step" : "steps";

  if (terminal.event.type === "job_cancelled") {
    const cancelledId = terminal.event.cancelled_at_step_id;
    const idx = cancelledId
      ? plan.steps.findIndex((s) => s.step_id === cancelledId)
      : plan.steps.length;
    const completedCount = idx <= 0 ? 0 : idx;
    if (completedCount <= 0) {
      return `Cancelled before Step 1 of ${n}. No step changes were applied.`;
    }
    const range = completedCount === 1 ? "Step 1" : `Steps 1–${completedCount}`;
    return `Cancelled after Step ${Math.min(completedCount + 1, n)} of ${n}. ${range}'s changes were applied.`;
  }

  if (terminal.event.type === "job_completed") {
    return `Completed all ${n} ${m}.`;
  }

  if (terminal.event.type === "job_failed") {
    return `Plan failed after ${n} ${m}.`;
  }

  return null;
}

export type StepErrorView = {
  error_code: string;
  error_message: string;
  error_details_preview: string | null;
};

export function truncateErrorDetails(details: Record<string, unknown> | null): string | null {
  if (!details || Object.keys(details).length === 0) return null;
  const raw = JSON.stringify(details);
  if (raw.length <= 160) return raw;
  return `${raw.slice(0, 157)}…`;
}

export function buildStepErrors(plan: Plan, events: SSEEvent[]): (StepErrorView | null)[] {
  const errors: (StepErrorView | null)[] = plan.steps.map(() => null);
  let lastRunningIdx = 0;

  for (const ev of events) {
    const payload = ev.event;
    if (payload.type === "step_started") {
      const idx = plan.steps.findIndex((s) => s.step_id === payload.step_id);
      if (idx >= 0) lastRunningIdx = idx;
    }
    if (payload.type === "step_failed") {
      const idx = plan.steps.findIndex((s) => s.step_id === payload.step_id);
      if (idx >= 0) {
        errors[idx] = {
          error_code: payload.error.error_code,
          error_message: payload.error.error_message,
          error_details_preview: truncateErrorDetails(payload.error.error_details),
        };
      }
    }
    if (payload.type === "runtime_error") {
      errors[lastRunningIdx] = {
        error_code: payload.error.error_code,
        error_message: payload.error.error_message,
        error_details_preview: truncateErrorDetails(payload.error.error_details),
      };
    }
  }

  return errors;
}

export function extractJobFailedError(events: SSEEvent[]): ErrorEnvelope | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const payload = events[i]!.event;
    if (payload.type === "job_failed") return payload.error;
  }
  return null;
}

export function shouldShowStalledCancelWarning(
  cancelClickedAtMs: number | null,
  events: SSEEvent[],
  nowMs: number,
): boolean {
  if (cancelClickedAtMs === null) return false;
  if (events.some((e) => e.event.type === "job_cancelled")) return false;
  return nowMs - cancelClickedAtMs >= 30_000;
}
