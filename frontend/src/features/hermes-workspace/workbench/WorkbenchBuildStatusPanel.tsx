import { cn } from "@/lib/utils";
import type { WorkbenchPreviewPhase } from "@/lib/ham/workbenchPreviewMessages";
import type { ManagedProviderBuildPhase } from "@/features/hermes-workspace/screens/chat/coding-plan/ManagedProviderBuildApprovalPanel";
import type { BuildGenerationPhase } from "@/features/hermes-workspace/screens/chat/coding-plan/codingPlanCardCopy";

export type WorkbenchBuildStatusValue =
  | "preparing-preview"
  | "preview-ready"
  | "ready-to-build"
  | "building"
  | "preview-updated"
  | "build-completed"
  | "checking"
  | "attention";

const STATUS_COPY: Record<WorkbenchBuildStatusValue, string> = {
  "preparing-preview": "Preparing preview…",
  "preview-ready": "Preview ready",
  "ready-to-build": "Ready to build",
  building: "Building…",
  "preview-updated": "Preview updated",
  "build-completed": "Build completed",
  checking: "Checking latest status…",
  attention: "Something needs attention",
};

/** Map the available workbench preview phase to a plain-language build status. */
export function buildStatusFromPreviewPhase(
  phase: WorkbenchPreviewPhase,
): WorkbenchBuildStatusValue {
  switch (phase) {
    case "ready":
      return "preview-ready";
    case "error":
      return "attention";
    case "preparing":
    case "starting":
      return "building";
    case "no_project":
    case "no_source":
    case "source_ready":
    default:
      return "ready-to-build";
  }
}

/**
 * Map the managed build approval lifecycle to a plain-language build status.
 *
 * Returns ``null`` when no managed build is active (``idle``) so the caller can
 * fall back to the preview-iframe phase. This lets the right-pane status shell
 * announce "Building…", "Build completed", and "Something needs attention" that
 * the preview phase alone cannot express — without exposing any build-kit
 * internals or duplicating the approval controls.
 */
export function buildStatusFromManagedPhase(
  phase: ManagedProviderBuildPhase,
): WorkbenchBuildStatusValue | null {
  switch (phase) {
    case "previewing":
      return "preparing-preview";
    case "previewed":
      return "preview-ready";
    case "launching":
    case "running":
      return "building";
    case "succeeded":
      return "build-completed";
    case "failed":
      return "attention";
    case "idle":
    default:
      return null;
  }
}

/**
 * Map the Builder Happy Path scaffold lifecycle to a plain-language status.
 *
 * Returns ``null`` for ``idle``/``ready`` so the preview-iframe phase takes over
 * once generation finishes (it then announces "Preview ready"/etc.). The
 * ``interrupted`` phase maps to a **recoverable** "Checking latest status…" —
 * never the failure-flavored "Something needs attention".
 */
export function buildStatusFromGenerationPhase(
  phase: BuildGenerationPhase,
): WorkbenchBuildStatusValue | null {
  switch (phase) {
    case "preparing":
      return "preparing-preview";
    case "generating":
      return "building";
    case "interrupted":
      return "checking";
    case "ready":
    case "idle":
    default:
      return null;
  }
}

/**
 * Presentational build-status shell for the workbench right pane. Renders one
 * plain-language lifecycle phrase for the supplied status — no controls, no
 * launch logic, no approval state.
 */
export function WorkbenchBuildStatusPanel({
  status,
  className,
}: {
  status: WorkbenchBuildStatusValue;
  className?: string;
}) {
  return (
    <div
      data-testid="hww-build-status-shell"
      data-build-status={status}
      className={cn(
        "rounded-md border border-white/[0.1] bg-black/25 px-2.5 py-1.5 text-[11px] font-medium text-white/75",
        className,
      )}
    >
      {STATUS_COPY[status]}
    </div>
  );
}
