import { cn } from "@/lib/utils";
import type { WorkbenchPreviewPhase } from "@/lib/ham/workbenchPreviewMessages";

export type WorkbenchBuildStatusValue =
  | "preview-ready"
  | "ready-to-build"
  | "building"
  | "preview-updated"
  | "build-completed"
  | "attention";

const STATUS_COPY: Record<WorkbenchBuildStatusValue, string> = {
  "preview-ready": "Preview ready",
  "ready-to-build": "Ready to build",
  building: "Building…",
  "preview-updated": "Preview updated",
  "build-completed": "Build completed",
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
