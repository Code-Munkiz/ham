import type { CodingConductorPreviewPayload } from "@/lib/ham/api";
import {
  shouldShowManagedBuildApproval,
  shouldShowOpencodeBuildApproval,
} from "@/features/hermes-workspace/screens/chat/coding-plan/codingPlanCardCopy";
import { ManagedBuildApprovalPanel } from "@/features/hermes-workspace/screens/chat/coding-plan/ManagedBuildApprovalPanel";
import { ManagedOpencodeBuildApprovalPanel } from "@/features/hermes-workspace/screens/chat/coding-plan/ManagedOpencodeBuildApprovalPanel";
import { cn } from "@/lib/utils";

export type WorkbenchManagedApprovalMountProps = {
  payload?: CodingConductorPreviewPayload | null;
  userPrompt?: string;
  className?: string;
};

/**
 * Right-pane host for the relocated managed build approval experience.
 *
 * Gates on the SAME exported pure predicates the chat card used, picks the
 * Droid vs OpenCode wrapper, and passes `projectId` + `userPrompt` into the
 * existing wrapper unchanged. The wrapper owns all launch/digest/polling
 * state, so there is a single source of launch truth. This must be mounted at
 * a stable location that does not unmount on workbench tab switch or mobile
 * right-pane collapse, so a running build's polling state survives.
 */
export function WorkbenchManagedApprovalMount({
  payload,
  userPrompt,
  className,
}: WorkbenchManagedApprovalMountProps) {
  if (!payload) return null;
  const projectId = payload.project.project_id;
  if (!projectId) return null;

  const showManaged = shouldShowManagedBuildApproval(payload);
  const showOpencode = shouldShowOpencodeBuildApproval(payload);
  if (!showManaged && !showOpencode) return null;

  return (
    <div
      data-testid="hww-right-pane-approval"
      className={cn(
        "shrink-0 border-b border-white/[0.08] bg-[#040d14]/92 px-3 pb-3 pt-2",
        className,
      )}
    >
      {showManaged ? (
        <ManagedBuildApprovalPanel projectId={projectId} userPrompt={userPrompt ?? ""} />
      ) : (
        <ManagedOpencodeBuildApprovalPanel projectId={projectId} userPrompt={userPrompt ?? ""} />
      )}
    </div>
  );
}
