import * as React from "react";

import type { CodingConductorCandidate, CodingConductorPreviewPayload } from "@/lib/ham/api";
import { sanitizeConductorUserFacingLine } from "@/lib/ham/conductorUiMessaging";
import { cn } from "@/lib/utils";

import {
  CODING_PLAN_LAUNCH_DISABLED_TITLE,
  CODING_PLAN_NO_LAUNCH_FOOTER,
  approvalCopyForCard,
  cardLabelForCandidate,
  confidenceBadgeForCard,
  emptyStateHeadlineForCard,
  outputKindCopyForCard,
  taskKindDisplayForCard,
} from "./codingPlanCardCopy";
import { ManagedBuildApprovalPanel } from "./ManagedBuildApprovalPanel";

export type CodingPlanCardProps = {
  payload: CodingConductorPreviewPayload;
  userPrompt?: string;
  className?: string;
};

function shouldShowManagedBuildApproval(payload: CodingConductorPreviewPayload): boolean {
  const chosen = payload.chosen;
  if (!chosen || chosen.provider !== "factory_droid_build" || !chosen.available) {
    return false;
  }
  const project = payload.project;
  if (!project.found || !project.project_id) return false;
  const target = (project.output_target || "").trim();
  if (target !== "managed_workspace") return false;
  if (project.has_workspace_id === false) return false;
  return true;
}

const BADGE_CLASS =
  "rounded-full border border-white/[0.12] bg-white/[0.04] px-2 py-0.5 text-[10px] uppercase tracking-wide text-white/70";

function CandidateBlockers({ blockers }: { blockers: string[] }) {
  if (!blockers.length) return null;
  return (
    <ul className="mt-1 space-y-0.5 text-[11px] text-amber-200/85" data-hww-coding-plan="blockers">
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

function CandidateRow({
  candidate,
  highlighted,
}: {
  candidate: CodingConductorCandidate;
  highlighted: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2",
        highlighted
          ? "border-emerald-300/30 bg-emerald-300/[0.05]"
          : "border-white/[0.08] bg-white/[0.02]",
      )}
      data-hww-coding-plan="candidate-row"
      data-provider={candidate.provider}
      data-available={candidate.available ? "1" : "0"}
    >
      <div className="flex items-center gap-2">
        <span className="text-[12px] font-semibold text-white/90">
          {cardLabelForCandidate(candidate)}
        </span>
        <span className={BADGE_CLASS}>{outputKindCopyForCard(candidate.output_kind)}</span>
        {candidate.available ? null : (
          <span
            className={cn(BADGE_CLASS, "border-amber-300/40 text-amber-200/85")}
            data-hww-coding-plan="blocked-pill"
          >
            Blocked
          </span>
        )}
      </div>
      <p className="mt-1 text-[11px] leading-snug text-white/65">{candidate.reason}</p>
      <CandidateBlockers blockers={candidate.blockers} />
    </div>
  );
}

/**
 * Read-only chat card surfacing the conductor preview.
 *
 * Phase 2B: NO launch button. The lone CTA is rendered as a disabled
 * placeholder so the user understands the next step is intentional, not
 * missing. Tests assert that the placeholder is non-interactive.
 */
export function CodingPlanCard({ payload, userPrompt, className }: CodingPlanCardProps) {
  const chosen = payload.chosen;
  const alts = payload.candidates.filter((c) => c !== chosen);
  const headline = emptyStateHeadlineForCard(payload);
  const taskLabel = taskKindDisplayForCard(payload.task_kind);
  const conf = confidenceBadgeForCard(payload.task_confidence);
  const showManagedApproval = shouldShowManagedBuildApproval(payload);

  const [showAlternatives, setShowAlternatives] = React.useState(false);

  return (
    <section
      className={cn(
        "rounded-lg border border-white/[0.1] bg-[#070b0f] p-3 text-white/85 shadow-[0_4px_14px_rgba(0,0,0,0.32)]",
        className,
      )}
      role="region"
      aria-label="HAM coding plan recommendation"
      data-hww-coding-plan="card"
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-white/55">
          HAM coding plan
        </span>
        <span className={BADGE_CLASS}>{taskLabel}</span>
        <span className={BADGE_CLASS} data-hww-coding-plan="task-confidence" data-confidence={conf}>
          {`Confidence: ${conf}`}
        </span>
      </header>

      <h3
        className="mt-2 text-[13px] font-semibold tracking-tight text-white"
        data-hww-coding-plan="headline"
      >
        {headline}
      </h3>
      <p
        className="mt-1 text-[12px] leading-snug text-white/70"
        data-hww-coding-plan="recommendation-reason"
      >
        {payload.recommendation_reason}
      </p>

      {chosen ? (
        <div className="mt-3 grid gap-1.5 text-[11px] text-white/70">
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={BADGE_CLASS}
            >{`Output: ${outputKindCopyForCard(chosen.output_kind)}`}</span>
            <span className={BADGE_CLASS}>
              {chosen.will_modify_code ? "Will modify code" : "Won't modify code"}
            </span>
            <span className={BADGE_CLASS}>
              {chosen.will_open_pull_request ? "Opens a pull request" : "No pull request"}
            </span>
            {chosen.requires_operator ? <span className={BADGE_CLASS}>Operator-only</span> : null}
          </div>
          <p className="leading-snug" data-hww-coding-plan="approval-copy">
            {approvalCopyForCard(payload.approval_kind)}
          </p>
        </div>
      ) : null}

      {payload.blockers.length ? (
        <ul
          className="mt-3 space-y-0.5 text-[11px] text-amber-200/85"
          data-hww-coding-plan="response-blockers"
        >
          {payload.blockers.map((b, i) => {
            const safe = sanitizeConductorUserFacingLine(b);
            return (
              <li key={`${i}-${safe}`} className="flex gap-1.5 leading-snug">
                <span aria-hidden>•</span>
                <span>{safe}</span>
              </li>
            );
          })}
        </ul>
      ) : null}

      {chosen && chosen.blockers.length ? <CandidateBlockers blockers={chosen.blockers} /> : null}

      {alts.length ? (
        <div className="mt-3">
          <button
            type="button"
            className="text-[11px] font-medium text-cyan-300/85 hover:text-cyan-200"
            onClick={() => setShowAlternatives((v) => !v)}
            aria-expanded={showAlternatives}
            data-hww-coding-plan="alternatives-toggle"
          >
            {showAlternatives
              ? "Hide alternatives"
              : `Show ${alts.length} alternative${alts.length === 1 ? "" : "s"}`}
          </button>
          {showAlternatives ? (
            <div className="mt-2 grid gap-1.5" role="list" data-hww-coding-plan="alternatives">
              {alts.map((c) => (
                <CandidateRow key={c.provider} candidate={c} highlighted={false} />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {showManagedApproval && payload.project.project_id ? (
        <ManagedBuildApprovalPanel
          projectId={payload.project.project_id}
          userPrompt={userPrompt ?? ""}
        />
      ) : (
        <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-2">
          <p
            className="text-[10px] leading-snug text-white/45"
            data-hww-coding-plan="no-launch-footer"
          >
            {CODING_PLAN_NO_LAUNCH_FOOTER}
          </p>
          <button
            type="button"
            disabled
            aria-disabled="true"
            title={CODING_PLAN_LAUNCH_DISABLED_TITLE}
            className="cursor-not-allowed rounded-md border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[11px] font-medium text-white/40"
            data-hww-coding-plan="launch-cta-disabled"
            data-launch-enabled="0"
          >
            Approve launch (later step)
          </button>
        </footer>
      )}
    </section>
  );
}
