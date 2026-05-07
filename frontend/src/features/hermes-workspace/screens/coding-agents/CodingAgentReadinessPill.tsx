import { CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { CODING_AGENT_LABELS } from "./codingAgentLabels";
import type { CodingAgentReadiness } from "../../adapters/codingAgentsAdapter";

export function CodingAgentReadinessPill({
  readiness,
  className,
}: {
  readiness: CodingAgentReadiness;
  className?: string;
}) {
  const isReady = readiness === "ready";
  const Icon = isReady ? CheckCircle2 : AlertCircle;
  const label = isReady
    ? CODING_AGENT_LABELS.readinessReady
    : CODING_AGENT_LABELS.readinessNeedsSetup;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
        isReady
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
          : "border-amber-500/30 bg-amber-500/10 text-amber-200",
        className,
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}
