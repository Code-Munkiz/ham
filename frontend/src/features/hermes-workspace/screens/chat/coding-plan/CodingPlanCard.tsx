import * as React from "react";

import type { CodingConductorPreviewPayload } from "@/lib/ham/api";
import { sanitizeConductorUserFacingLine } from "@/lib/ham/conductorUiMessaging";
import { cn } from "@/lib/utils";

import {
  CODING_PLAN_RIGHT_PANE_POINTER,
  OPENCODE_PREFERRED_CTA,
  OPENCODE_PREFERRED_HINT,
  OPENCODE_PREFERRED_LOADING,
  shouldShowManagedBuildApproval,
  shouldShowOpencodeBuildApproval,
  shouldShowOpenCodeAffordance,
} from "./codingPlanCardCopy";

export type CodingPlanCardProps = {
  payload: CodingConductorPreviewPayload;
  userPrompt?: string;
  className?: string;
  onPreferProvider?: (provider: "opencode_cli") => void;
  preferringProvider?: "opencode_cli" | null;
  builderName?: string;
};

const READY_TITLE = "Ready to build";
const READY_COPY = "HAM prepared a safe build preview. Review and approve when you're ready.";

function ActionableBlockers({ blockers }: { blockers: string[] }) {
  if (!blockers.length) return null;
  return (
    <ul
      className="mt-2 space-y-0.5 text-[11px] text-amber-200/85"
      data-hww-coding-plan="response-blockers"
    >
      {blockers.map((b, i) => {
        const safe = sanitizeConductorUserFacingLine(b);
        return (
          <li key={`${i}-${safe}`} className="flex gap-1.5 leading-snug">
            <span aria-hidden>•</span>
            <span>{safe}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Minimal chat approval strip for managed build preview/launch.
 * Provider/candidate dashboard details stay hidden in normal UX.
 */
export function CodingPlanCard({
  payload,
  userPrompt,
  className,
  onPreferProvider,
  preferringProvider = null,
}: CodingPlanCardProps) {
  const showManagedApproval = shouldShowManagedBuildApproval(payload);
  const showOpencodeApproval = shouldShowOpencodeBuildApproval(payload);
  const showOpencodeAffordance = Boolean(onPreferProvider) && shouldShowOpenCodeAffordance(payload);
  const opencodePreferring = preferringProvider === "opencode_cli";
  const hasApprovalPanel = showManagedApproval || showOpencodeApproval;
  const actionableBlockers = React.useMemo(() => {
    const merged = [...payload.blockers, ...(payload.chosen?.blockers ?? [])];
    return merged.filter((line) => line.trim().length > 0);
  }, [payload.blockers, payload.chosen?.blockers]);
  const showActionableBlockers = !hasApprovalPanel && actionableBlockers.length > 0;

  return (
    <section
      className={cn(
        "rounded-md border border-white/[0.08] bg-[#070b0f]/90 p-3 text-white/85",
        className,
      )}
      role="region"
      aria-label="HAM build approval"
      data-hww-coding-plan="card"
    >
      <h3
        className="text-[13px] font-semibold tracking-tight text-white"
        data-hww-coding-plan="ready-title"
      >
        {READY_TITLE}
      </h3>
      <p className="mt-1 text-[11px] leading-snug text-white/65" data-hww-coding-plan="ready-copy">
        {READY_COPY}
      </p>
      {showActionableBlockers ? <ActionableBlockers blockers={actionableBlockers} /> : null}

      {showOpencodeAffordance ? (
        <div
          className="mt-3 flex flex-wrap items-center gap-2"
          data-hww-coding-plan="opencode-affordance"
        >
          <button
            type="button"
            onClick={() => onPreferProvider?.("opencode_cli")}
            disabled={opencodePreferring}
            aria-disabled={opencodePreferring}
            aria-busy={opencodePreferring}
            className="rounded-md border border-cyan-300/35 bg-cyan-300/[0.06] px-2.5 py-1 text-[11px] font-medium text-cyan-100 hover:bg-cyan-300/[0.12] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/60 disabled:cursor-not-allowed disabled:opacity-60"
            data-hww-coding-plan="prefer-opencode-cta"
          >
            {opencodePreferring ? OPENCODE_PREFERRED_LOADING : OPENCODE_PREFERRED_CTA}
          </button>
          <span className="text-[10px] leading-snug text-white/55">{OPENCODE_PREFERRED_HINT}</span>
        </div>
      ) : null}

      {hasApprovalPanel ? (
        <p
          className="mt-3 text-[11px] leading-snug text-cyan-100/85"
          data-hww-coding-plan="right-pane-pointer"
        >
          {CODING_PLAN_RIGHT_PANE_POINTER}
        </p>
      ) : null}
    </section>
  );
}
