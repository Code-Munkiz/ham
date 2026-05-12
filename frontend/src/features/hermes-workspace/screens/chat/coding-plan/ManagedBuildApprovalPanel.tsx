import * as React from "react";

import {
  launchDroidBuild,
  previewDroidBuild,
  shortenHamApiErrorMessage,
  type DroidBuildLaunchPayload,
  type DroidBuildPreviewPayload,
} from "@/lib/ham/api";
import { cn } from "@/lib/utils";

import {
  MANAGED_BUILD_APPROVAL_BODY,
  MANAGED_BUILD_APPROVAL_CHECKBOX,
  MANAGED_BUILD_APPROVAL_HEADLINE,
  MANAGED_BUILD_FAILURE_HEADLINE,
  MANAGED_BUILD_LAUNCH_BUSY,
  MANAGED_BUILD_LAUNCH_CTA,
  MANAGED_BUILD_NO_PR_NOTE,
  MANAGED_BUILD_PREVIEW_BUSY,
  MANAGED_BUILD_PREVIEW_CTA,
  MANAGED_BUILD_SUCCESS_HEADLINE,
} from "./codingPlanCardCopy";

export type ManagedBuildApprovalPanelProps = {
  projectId: string;
  userPrompt: string;
  className?: string;
};

type PanelState =
  | { phase: "idle" }
  | { phase: "previewing" }
  | { phase: "previewed"; preview: DroidBuildPreviewPayload; approved: boolean }
  | { phase: "launching"; preview: DroidBuildPreviewPayload }
  | { phase: "succeeded"; result: DroidBuildLaunchPayload }
  | { phase: "failed"; message: string };

function isManagedSnapshotRef(
  ref: Record<string, unknown> | null | undefined,
): ref is Record<string, unknown> {
  return Boolean(ref && typeof ref === "object");
}

function readStringField(
  ref: Record<string, unknown> | null | undefined,
  key: string,
): string | null {
  if (!isManagedSnapshotRef(ref)) return null;
  const v = ref[key];
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function readNumberField(
  ref: Record<string, unknown> | null | undefined,
  key: string,
): number | null {
  if (!isManagedSnapshotRef(ref)) return null;
  const v = ref[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * Approval surface for `output_target == "managed_workspace"` builds.
 *
 * Wired only by :func:`CodingPlanCard` when the chosen provider is
 * `factory_droid_build` and the project's output target is managed.
 * Drives `POST /api/droid/build/preview` then `/launch` with the
 * sanitized fields returned from the conductor preview. Never opens a
 * pull request and never surfaces workflow ids, runner URLs, argv, or
 * token env names — the API already strips those server-side.
 */
export function ManagedBuildApprovalPanel({
  projectId,
  userPrompt,
  className,
}: ManagedBuildApprovalPanelProps) {
  const [state, setState] = React.useState<PanelState>({ phase: "idle" });

  const trimmedPrompt = userPrompt.trim();
  const canStart = Boolean(projectId) && trimmedPrompt.length > 0;

  const handlePreview = React.useCallback(async () => {
    if (!canStart) return;
    setState({ phase: "previewing" });
    try {
      const preview = await previewDroidBuild({
        project_id: projectId,
        user_prompt: trimmedPrompt,
      });
      setState({ phase: "previewed", preview, approved: false });
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Preview failed. Try again in a moment.";
      setState({ phase: "failed", message: shortenHamApiErrorMessage(msg) });
    }
  }, [canStart, projectId, trimmedPrompt]);

  const handleToggleApproval = React.useCallback(() => {
    setState((s) => (s.phase === "previewed" ? { ...s, approved: !s.approved } : s));
  }, []);

  const handleLaunch = React.useCallback(async () => {
    if (state.phase !== "previewed" || !state.approved) return;
    const preview = state.preview;
    setState({ phase: "launching", preview });
    try {
      const result = await launchDroidBuild({
        project_id: preview.project_id,
        user_prompt: preview.user_prompt,
        proposal_digest: preview.proposal_digest,
        base_revision: preview.base_revision,
        confirmed: true,
        accept_pr: true,
      });
      if (!result.ok) {
        setState({
          phase: "failed",
          message:
            shortenHamApiErrorMessage(result.error_summary || "")
            || "The build did not complete.",
        });
        return;
      }
      setState({ phase: "succeeded", result });
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Build failed. Try again in a moment.";
      setState({ phase: "failed", message: shortenHamApiErrorMessage(msg) });
    }
  }, [state]);

  const handleReset = React.useCallback(() => {
    setState({ phase: "idle" });
  }, []);

  const isPreviewing = state.phase === "previewing";
  const isLaunching = state.phase === "launching";
  const previewed = state.phase === "previewed" ? state.preview : null;
  const approved = state.phase === "previewed" ? state.approved : false;
  const launchDisabled = !previewed || !approved || isLaunching;

  return (
    <section
      className={cn(
        "mt-3 rounded-md border border-emerald-300/20 bg-emerald-300/[0.04] p-3",
        className,
      )}
      data-hww-coding-plan="managed-build-approval"
      data-phase={state.phase}
      aria-label="Managed workspace build approval"
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-emerald-200/85">
          Managed workspace build
        </span>
      </header>
      <h4
        className="mt-1 text-[12px] font-semibold text-white"
        data-hww-coding-plan="managed-build-headline"
      >
        {state.phase === "succeeded"
          ? MANAGED_BUILD_SUCCESS_HEADLINE
          : state.phase === "failed"
            ? MANAGED_BUILD_FAILURE_HEADLINE
            : MANAGED_BUILD_APPROVAL_HEADLINE}
      </h4>

      {state.phase === "idle" || isPreviewing ? (
        <>
          <p className="mt-1 text-[11px] leading-snug text-white/70">
            {MANAGED_BUILD_APPROVAL_BODY}
          </p>
          <p className="mt-1 text-[10px] leading-snug text-white/50">
            {MANAGED_BUILD_NO_PR_NOTE}
          </p>
          <div className="mt-2">
            <button
              type="button"
              onClick={handlePreview}
              disabled={!canStart || isPreviewing}
              className={cn(
                "rounded-md border px-2.5 py-1 text-[11px] font-medium",
                !canStart || isPreviewing
                  ? "cursor-not-allowed border-white/[0.08] bg-white/[0.03] text-white/40"
                  : "border-emerald-300/40 bg-emerald-300/[0.08] text-emerald-50 hover:bg-emerald-300/[0.12]",
              )}
              data-hww-coding-plan="managed-build-preview-cta"
            >
              {isPreviewing ? MANAGED_BUILD_PREVIEW_BUSY : MANAGED_BUILD_PREVIEW_CTA}
            </button>
          </div>
        </>
      ) : null}

      {previewed && (state.phase === "previewed" || isLaunching) ? (
        <div className="mt-2 grid gap-2 text-[11px] text-white/75">
          <p data-hww-coding-plan="managed-build-summary">{previewed.summary}</p>
          <p className="text-[10px] text-white/50">
            {MANAGED_BUILD_NO_PR_NOTE}
          </p>
          <label
            className="mt-1 flex cursor-pointer items-start gap-2"
            data-hww-coding-plan="managed-build-approve-checkbox"
          >
            <input
              type="checkbox"
              className="mt-0.5"
              checked={approved}
              disabled={isLaunching}
              onChange={handleToggleApproval}
              aria-checked={approved}
            />
            <span className="leading-snug">{MANAGED_BUILD_APPROVAL_CHECKBOX}</span>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleLaunch}
              disabled={launchDisabled}
              aria-disabled={launchDisabled}
              className={cn(
                "rounded-md border px-2.5 py-1 text-[11px] font-medium",
                launchDisabled
                  ? "cursor-not-allowed border-white/[0.08] bg-white/[0.03] text-white/40"
                  : "border-emerald-300/40 bg-emerald-300/[0.12] text-emerald-50 hover:bg-emerald-300/[0.18]",
              )}
              data-hww-coding-plan="managed-build-launch-cta"
              data-launch-enabled={launchDisabled ? "0" : "1"}
            >
              {isLaunching ? MANAGED_BUILD_LAUNCH_BUSY : MANAGED_BUILD_LAUNCH_CTA}
            </button>
            {isLaunching ? null : (
              <button
                type="button"
                onClick={handleReset}
                className="text-[11px] text-white/55 hover:text-white/80"
                data-hww-coding-plan="managed-build-reset"
              >
                Discard preview
              </button>
            )}
          </div>
        </div>
      ) : null}

      {state.phase === "succeeded" ? (
        <ManagedBuildSuccessSummary result={state.result} onReset={handleReset} />
      ) : null}

      {state.phase === "failed" ? (
        <div className="mt-2 grid gap-1.5 text-[11px] text-amber-200/90">
          <p data-hww-coding-plan="managed-build-error">{state.message}</p>
          <div>
            <button
              type="button"
              onClick={handleReset}
              className="rounded-md border border-amber-300/40 bg-amber-300/[0.08] px-2.5 py-1 text-[11px] font-medium text-amber-50 hover:bg-amber-300/[0.12]"
              data-hww-coding-plan="managed-build-retry"
            >
              Start over
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ManagedBuildSuccessSummary({
  result,
  onReset,
}: {
  result: DroidBuildLaunchPayload;
  onReset: () => void;
}) {
  const snapshotId = readStringField(result.output_ref, "snapshot_id");
  const previewUrl = readStringField(result.output_ref, "preview_url");
  const changedCount = readNumberField(result.output_ref, "changed_paths_count");
  const neutral = readStringField(result.output_ref, "neutral_outcome");
  return (
    <div className="mt-2 grid gap-1.5 text-[11px] text-white/80">
      <ul className="grid gap-0.5">
        {snapshotId ? (
          <li data-hww-coding-plan="managed-build-snapshot-id">
            <span className="text-white/55">Snapshot id: </span>
            <span className="font-mono text-white/85">{snapshotId}</span>
          </li>
        ) : null}
        {previewUrl ? (
          <li data-hww-coding-plan="managed-build-preview-url">
            <a
              href={previewUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="text-cyan-300/90 hover:text-cyan-200"
            >
              Open snapshot preview
            </a>
          </li>
        ) : null}
        {typeof changedCount === "number" ? (
          <li data-hww-coding-plan="managed-build-changed-count">
            <span className="text-white/55">Changed paths: </span>
            <span className="text-white/85">{changedCount}</span>
          </li>
        ) : null}
        {neutral ? (
          <li data-hww-coding-plan="managed-build-neutral-outcome">
            <span className="text-white/55">Outcome: </span>
            <span className="text-white/85">{neutral}</span>
          </li>
        ) : null}
      </ul>
      <p className="text-[10px] leading-snug text-white/50">{MANAGED_BUILD_NO_PR_NOTE}</p>
      <div>
        <button
          type="button"
          onClick={onReset}
          className="rounded-md border border-white/[0.1] bg-white/[0.04] px-2.5 py-1 text-[11px] font-medium text-white/75 hover:bg-white/[0.08]"
          data-hww-coding-plan="managed-build-done"
        >
          Done
        </button>
      </div>
    </div>
  );
}
