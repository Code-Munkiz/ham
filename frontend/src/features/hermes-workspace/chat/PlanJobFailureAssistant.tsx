import type { ErrorEnvelope } from "@/lib/ham/builderPlan";
import { Button } from "@/components/ui/button";

export type PlanJobFailureAssistantProps = {
  error: ErrorEnvelope;
  onTryAgain: () => void;
  onEditReplan: () => void;
};

export function PlanJobFailureAssistant({
  error,
  onTryAgain,
  onEditReplan,
}: PlanJobFailureAssistantProps) {
  return (
    <div
      className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2.5 text-[12px] text-red-50"
      data-testid="plan-job-failure-assistant"
    >
      <p className="font-medium text-red-100">Plan failed: {error.error_message}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          data-testid="plan-job-failure-try-again"
          onClick={onTryAgain}
        >
          Try again
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="border-red-400/30 bg-transparent text-red-100 hover:bg-red-500/20"
          data-testid="plan-job-failure-edit-replan"
          onClick={onEditReplan}
        >
          Edit and re-plan
        </Button>
      </div>
    </div>
  );
}
