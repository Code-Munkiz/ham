import * as React from "react";

import {
  launchDroidBuild,
  previewDroidBuild,
  type DroidBuildLaunchPayload,
  type DroidBuildPreviewPayload,
} from "@/lib/ham/api";

import {
  MANAGED_BUILD_APPROVAL_BODY,
  MANAGED_BUILD_APPROVAL_CHECKBOX,
  MANAGED_BUILD_APPROVAL_HEADLINE,
  MANAGED_BUILD_FAILURE_HEADLINE,
  MANAGED_BUILD_KEEP_BUILDING_CTA,
  MANAGED_BUILD_LAUNCH_BUSY,
  MANAGED_BUILD_LAUNCH_CTA,
  MANAGED_BUILD_NO_PR_NOTE,
  MANAGED_BUILD_PREVIEW_BUSY,
  MANAGED_BUILD_PREVIEW_CTA,
  MANAGED_BUILD_PREVIEW_LINK,
  MANAGED_BUILD_SUCCESS_HEADLINE,
  MANAGED_BUILD_TECHNICAL_DETAILS_SUMMARY,
  MANAGED_BUILD_VIEW_CHANGES_LINK,
  managedBuildChangedPathsLine,
} from "./codingPlanCardCopy";
import {
  ManagedProviderBuildApprovalPanel,
  type ManagedProviderBuildConfig,
} from "./ManagedProviderBuildApprovalPanel";

export type ManagedBuildApprovalPanelProps = {
  projectId: string;
  userPrompt: string;
  className?: string;
};

const droidConfig: ManagedProviderBuildConfig<DroidBuildPreviewPayload, DroidBuildLaunchPayload> = {
  providerKey: "factory_droid_build",
  testIdPrefix: "managed-build",
  ariaLabel: "Managed workspace build approval",
  copy: {
    headline: MANAGED_BUILD_APPROVAL_HEADLINE,
    body: MANAGED_BUILD_APPROVAL_BODY,
    noPrNote: MANAGED_BUILD_NO_PR_NOTE,
    checkbox: MANAGED_BUILD_APPROVAL_CHECKBOX,
    previewCta: MANAGED_BUILD_PREVIEW_CTA,
    previewBusy: MANAGED_BUILD_PREVIEW_BUSY,
    launchCta: MANAGED_BUILD_LAUNCH_CTA,
    launchBusy: MANAGED_BUILD_LAUNCH_BUSY,
    successHeadline: MANAGED_BUILD_SUCCESS_HEADLINE,
    failureHeadline: MANAGED_BUILD_FAILURE_HEADLINE,
    previewLink: MANAGED_BUILD_PREVIEW_LINK,
    viewChangesLink: MANAGED_BUILD_VIEW_CHANGES_LINK,
    technicalDetailsSummary: MANAGED_BUILD_TECHNICAL_DETAILS_SUMMARY,
    keepBuildingCta: MANAGED_BUILD_KEEP_BUILDING_CTA,
    laneLabel: "Managed workspace build",
    discardPreviewLabel: "Discard preview",
    startOverLabel: "Start over",
    defaultPreviewError: "Preview failed. Try again in a moment.",
    defaultLaunchError: "Build failed. Try again in a moment.",
    failureFallbackMessage: "The build did not complete.",
    snapshotIdLabel: "Snapshot id:",
    outcomeLabel: "Outcome:",
  },
  preview: (payload) =>
    previewDroidBuild({
      project_id: payload.project_id,
      user_prompt: payload.user_prompt,
    }),
  launch: (payload) =>
    launchDroidBuild({
      project_id: payload.project_id,
      user_prompt: payload.user_prompt,
      proposal_digest: payload.proposal_digest,
      base_revision: payload.base_revision,
      confirmed: payload.confirmed,
      accept_pr: true,
    }),
  changedPathsLine: managedBuildChangedPathsLine,
};

/**
 * Approval surface for `output_target == "managed_workspace"` builds
 * driven by the Factory Droid build lane.
 *
 * Wired only by :func:`CodingPlanCard` when the chosen provider is
 * `factory_droid_build` and the project's output target is managed.
 * Internally delegates to {@link ManagedProviderBuildApprovalPanel}
 * with a Droid-specific config (preview / launch endpoints, copy slots,
 * and `accept_pr: true` for the legacy launch body).
 */
export function ManagedBuildApprovalPanel({
  projectId,
  userPrompt,
  className,
}: ManagedBuildApprovalPanelProps) {
  return (
    <ManagedProviderBuildApprovalPanel
      projectId={projectId}
      userPrompt={userPrompt}
      className={className}
      config={droidConfig}
    />
  );
}
