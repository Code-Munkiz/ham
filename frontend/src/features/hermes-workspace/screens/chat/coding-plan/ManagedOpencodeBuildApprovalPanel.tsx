import * as React from "react";

import {
  launchOpencodeBuild,
  previewOpencodeBuild,
  type OpencodeBuildLaunchPayload,
  type OpencodeBuildPreviewPayload,
} from "@/lib/ham/api";

import {
  normieFailMessageForOpencode,
  OPENCODE_BUILD_APPROVAL_BODY,
  OPENCODE_BUILD_APPROVAL_CHECKBOX,
  OPENCODE_BUILD_APPROVAL_HEADLINE,
  OPENCODE_BUILD_FAILURE_HEADLINE,
  OPENCODE_BUILD_KEEP_BUILDING_CTA,
  OPENCODE_BUILD_LAUNCH_BUSY,
  OPENCODE_BUILD_LAUNCH_CTA,
  OPENCODE_BUILD_NO_PR_NOTE,
  OPENCODE_BUILD_PREVIEW_BUSY,
  OPENCODE_BUILD_PREVIEW_CTA,
  OPENCODE_BUILD_PREVIEW_LINK,
  OPENCODE_BUILD_RUNNING_HEADLINE,
  OPENCODE_BUILD_RUNNING_NOTE,
  OPENCODE_BUILD_SUCCESS_HEADLINE,
  OPENCODE_BUILD_TECHNICAL_DETAILS_SUMMARY,
  OPENCODE_BUILD_VIEW_CHANGES_LINK,
  opencodeBuildChangedPathsLine,
} from "./codingPlanCardCopy";
import {
  ManagedProviderBuildApprovalPanel,
  type ManagedProviderBuildConfig,
} from "./ManagedProviderBuildApprovalPanel";

export type ManagedOpencodeBuildApprovalPanelProps = {
  projectId: string;
  userPrompt: string;
  model?: string | null;
  className?: string;
};

function buildOpencodeConfig(
  model?: string | null,
): ManagedProviderBuildConfig<OpencodeBuildPreviewPayload, OpencodeBuildLaunchPayload> {
  return {
    providerKey: "opencode_managed_build",
    testIdPrefix: "opencode-build",
    ariaLabel: "OpenCode managed workspace build approval",
    copy: {
      headline: OPENCODE_BUILD_APPROVAL_HEADLINE,
      body: OPENCODE_BUILD_APPROVAL_BODY,
      noPrNote: OPENCODE_BUILD_NO_PR_NOTE,
      checkbox: OPENCODE_BUILD_APPROVAL_CHECKBOX,
      previewCta: OPENCODE_BUILD_PREVIEW_CTA,
      previewBusy: OPENCODE_BUILD_PREVIEW_BUSY,
      launchCta: OPENCODE_BUILD_LAUNCH_CTA,
      launchBusy: OPENCODE_BUILD_LAUNCH_BUSY,
      successHeadline: OPENCODE_BUILD_SUCCESS_HEADLINE,
      failureHeadline: OPENCODE_BUILD_FAILURE_HEADLINE,
      previewLink: OPENCODE_BUILD_PREVIEW_LINK,
      viewChangesLink: OPENCODE_BUILD_VIEW_CHANGES_LINK,
      technicalDetailsSummary: OPENCODE_BUILD_TECHNICAL_DETAILS_SUMMARY,
      keepBuildingCta: OPENCODE_BUILD_KEEP_BUILDING_CTA,
      laneLabel: "OpenCode build",
      discardPreviewLabel: "Discard preview",
      startOverLabel: "Start over",
      defaultPreviewError: "Preview failed. Try again in a moment.",
      defaultLaunchError: "Build failed. Try again in a moment.",
      failureFallbackMessage: "The build did not complete.",
      snapshotIdLabel: "Snapshot id:",
      outcomeLabel: "Outcome:",
    },
    preview: (payload) =>
      previewOpencodeBuild({
        project_id: payload.project_id,
        user_prompt: payload.user_prompt,
        model: payload.model,
      }),
    launch: (payload) =>
      launchOpencodeBuild({
        project_id: payload.project_id,
        user_prompt: payload.user_prompt,
        model: payload.model,
        proposal_digest: payload.proposal_digest,
        base_revision: payload.base_revision,
        confirmed: payload.confirmed,
      }),
    changedPathsLine: opencodeBuildChangedPathsLine,
    model: model ?? null,
    runningHeadline: OPENCODE_BUILD_RUNNING_HEADLINE,
    runningNote: OPENCODE_BUILD_RUNNING_NOTE,
    normieFailMessageForStatusReason: normieFailMessageForOpencode,
  };
}

/**
 * Approval surface for `output_target == "managed_workspace"` builds
 * driven by the OpenCode lane (via the in-process launch proxy).
 *
 * Wired only by :func:`CodingPlanCard` when the chosen provider is
 * `opencode_cli` and the project's output target is managed. Internally
 * delegates to {@link ManagedProviderBuildApprovalPanel} with an
 * OpenCode-specific config. The browser never sees the OpenCode exec
 * token; the proxy reads it from the server-side environment only.
 */
export function ManagedOpencodeBuildApprovalPanel({
  projectId,
  userPrompt,
  model,
  className,
}: ManagedOpencodeBuildApprovalPanelProps) {
  const config = React.useMemo(() => buildOpencodeConfig(model), [model]);
  return (
    <ManagedProviderBuildApprovalPanel
      projectId={projectId}
      userPrompt={userPrompt}
      className={className}
      config={config}
    />
  );
}
