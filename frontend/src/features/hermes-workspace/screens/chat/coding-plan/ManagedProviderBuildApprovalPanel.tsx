import * as React from "react";

import { fetchControlPlaneRun, shortenHamApiErrorMessage } from "@/lib/ham/api";
import {
  assertManagedBuildSmokePreflight,
  SmokePreflightError,
} from "@/lib/ham/managedBuildSmokePreflight";
import { cn } from "@/lib/utils";

const POLL_INTERVAL_MS = 3000;

export type ManagedProviderBuildOutputRef = Record<string, unknown> | null | undefined;

export interface ManagedProviderBuildPreviewLike {
  project_id: string;
  user_prompt: string;
  summary: string;
  proposal_digest: string;
  base_revision: string;
  model?: string | null;
}

export interface ManagedProviderBuildLaunchLike {
  ok: boolean | null;
  error_summary: string | null;
  output_ref?: ManagedProviderBuildOutputRef;
  ham_run_id?: string | null;
  control_plane_status?: string | null;
}

export interface ManagedProviderBuildCopy {
  headline: string;
  body: string;
  noPrNote: string;
  checkbox: string;
  previewCta: string;
  previewBusy: string;
  launchCta: string;
  launchBusy: string;
  successHeadline: string;
  failureHeadline: string;
  previewLink: string;
  viewChangesLink: string;
  technicalDetailsSummary: string;
  keepBuildingCta: string;
  laneLabel: string;
  discardPreviewLabel: string;
  startOverLabel: string;
  defaultPreviewError: string;
  defaultLaunchError: string;
  failureFallbackMessage: string;
  snapshotIdLabel: string;
  outcomeLabel: string;
}

export interface ManagedProviderBuildConfig<
  P extends ManagedProviderBuildPreviewLike,
  L extends ManagedProviderBuildLaunchLike,
> {
  providerKey: string;
  testIdPrefix: string;
  ariaLabel: string;
  copy: ManagedProviderBuildCopy;
  preview: (payload: {
    project_id: string;
    user_prompt: string;
    model?: string | null;
  }) => Promise<P>;
  launch: (payload: {
    project_id: string;
    user_prompt: string;
    model?: string | null;
    proposal_digest: string;
    base_revision: string;
    confirmed: true;
  }) => Promise<L>;
  changedPathsLine: (count: number) => string;
  model?: string | null;
  runningHeadline?: string;
  runningNote?: string;
  normieFailMessageForStatusReason?: (statusReason: string) => string | null;
  pollIntervalMs?: number;
}

export interface ManagedProviderBuildApprovalPanelProps<
  P extends ManagedProviderBuildPreviewLike,
  L extends ManagedProviderBuildLaunchLike,
> {
  projectId: string;
  userPrompt: string;
  className?: string;
  config: ManagedProviderBuildConfig<P, L>;
}

type PanelState<
  P extends ManagedProviderBuildPreviewLike,
  L extends ManagedProviderBuildLaunchLike,
> =
  | { phase: "idle" }
  | { phase: "previewing" }
  | { phase: "previewed"; preview: P; approved: boolean }
  | { phase: "launching"; preview: P }
  | { phase: "running"; hamRunId: string; preview: P }
  | { phase: "succeeded"; result: L }
  | { phase: "failed"; message: string };

function isOutputRefObject(ref: ManagedProviderBuildOutputRef): ref is Record<string, unknown> {
  return Boolean(ref && typeof ref === "object");
}

function readStringField(ref: ManagedProviderBuildOutputRef, key: string): string | null {
  if (!isOutputRefObject(ref)) return null;
  const v = ref[key];
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function readNumberField(ref: ManagedProviderBuildOutputRef, key: string): number | null {
  if (!isOutputRefObject(ref)) return null;
  const v = ref[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function ManagedProviderBuildApprovalPanel<
  P extends ManagedProviderBuildPreviewLike,
  L extends ManagedProviderBuildLaunchLike,
>({ projectId, userPrompt, className, config }: ManagedProviderBuildApprovalPanelProps<P, L>) {
  const prefix = config.testIdPrefix;
  const { copy } = config;
  const [state, setState] = React.useState<PanelState<P, L>>({ phase: "idle" });

  const trimmedPrompt = userPrompt.trim();
  const canStart = Boolean(projectId) && trimmedPrompt.length > 0;

  const handlePreview = React.useCallback(async () => {
    if (!canStart) return;
    setState({ phase: "previewing" });
    try {
      await assertManagedBuildSmokePreflight();
      const preview = await config.preview({
        project_id: projectId,
        user_prompt: trimmedPrompt,
        model: config.model,
      });
      setState({ phase: "previewed", preview, approved: false });
    } catch (err) {
      if (err instanceof SmokePreflightError) {
        setState({
          phase: "failed",
          message: `${err.code}: ${err.message}`,
        });
        return;
      }
      const msg = err instanceof Error ? err.message : copy.defaultPreviewError;
      setState({ phase: "failed", message: shortenHamApiErrorMessage(msg) });
    }
  }, [canStart, projectId, trimmedPrompt, config, copy.defaultPreviewError]);

  const handleToggleApproval = React.useCallback(() => {
    setState((s) => (s.phase === "previewed" ? { ...s, approved: !s.approved } : s));
  }, []);

  const handleLaunch = React.useCallback(async () => {
    if (state.phase !== "previewed" || !state.approved) return;
    const preview = state.preview;
    setState({ phase: "launching", preview });
    try {
      await assertManagedBuildSmokePreflight();
      const result = await config.launch({
        project_id: preview.project_id,
        user_prompt: preview.user_prompt,
        model: preview.model ?? config.model,
        proposal_digest: preview.proposal_digest,
        base_revision: preview.base_revision,
        confirmed: true,
      });
      if (result.control_plane_status === "running" && result.ham_run_id) {
        setState({ phase: "running", hamRunId: result.ham_run_id, preview });
        return;
      }
      if (!result.ok) {
        setState({
          phase: "failed",
          message:
            shortenHamApiErrorMessage(result.error_summary || "") || copy.failureFallbackMessage,
        });
        return;
      }
      setState({ phase: "succeeded", result });
    } catch (err) {
      if (err instanceof SmokePreflightError) {
        setState({
          phase: "failed",
          message: `${err.code}: ${err.message}`,
        });
        return;
      }
      const msg = err instanceof Error ? err.message : copy.defaultLaunchError;
      setState({ phase: "failed", message: shortenHamApiErrorMessage(msg) });
    }
  }, [state, config, copy.failureFallbackMessage, copy.defaultLaunchError]);

  const handleReset = React.useCallback(() => {
    setState({ phase: "idle" });
  }, []);

  const pollingRunId = state.phase === "running" ? state.hamRunId : null;

  React.useEffect(() => {
    if (!pollingRunId) return;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    const pollMs = config.pollIntervalMs ?? POLL_INTERVAL_MS;

    const tick = async () => {
      if (cancelled) return;
      try {
        const run = await fetchControlPlaneRun(pollingRunId);
        if (cancelled) return;
        if (run.status === "succeeded") {
          setState({
            phase: "succeeded",
            result: {
              ok: true,
              error_summary: null,
              output_ref: run.output_ref ?? null,
            } as L,
          });
        } else if (run.status === "failed" || run.status === "cancelled") {
          const normie = config.normieFailMessageForStatusReason?.(run.status_reason);
          const fallback =
            shortenHamApiErrorMessage(run.error_summary || "") || copy.failureFallbackMessage;
          setState({ phase: "failed", message: normie || fallback });
        } else {
          timeoutId = setTimeout(tick, pollMs);
        }
      } catch {
        if (!cancelled) timeoutId = setTimeout(tick, pollMs * 2);
      }
    };

    timeoutId = setTimeout(tick, pollMs);
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [pollingRunId, config, copy.failureFallbackMessage]);

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
      data-hww-coding-plan={`${prefix}-approval`}
      data-phase={state.phase}
      aria-label={config.ariaLabel}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-emerald-200/85">
          {copy.laneLabel}
        </span>
      </header>
      <h4
        className="mt-1 text-[12px] font-semibold text-white"
        data-hww-coding-plan={`${prefix}-headline`}
      >
        {state.phase === "succeeded"
          ? copy.successHeadline
          : state.phase === "failed"
            ? copy.failureHeadline
            : state.phase === "running"
              ? (config.runningHeadline ?? copy.headline)
              : copy.headline}
      </h4>

      {state.phase === "idle" || isPreviewing ? (
        <>
          <p className="mt-1 text-[11px] leading-snug text-white/70">{copy.body}</p>
          <p className="mt-1 text-[10px] leading-snug text-white/50">{copy.noPrNote}</p>
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
              data-hww-coding-plan={`${prefix}-preview-cta`}
            >
              {isPreviewing ? copy.previewBusy : copy.previewCta}
            </button>
          </div>
        </>
      ) : null}

      {previewed && (state.phase === "previewed" || isLaunching) ? (
        <div className="mt-2 grid gap-2 text-[11px] text-white/75">
          <p data-hww-coding-plan={`${prefix}-summary`}>{previewed.summary}</p>
          <p className="text-[10px] text-white/50">{copy.noPrNote}</p>
          <label
            className="mt-1 flex cursor-pointer items-start gap-2"
            data-hww-coding-plan={`${prefix}-approve-checkbox`}
          >
            <input
              type="checkbox"
              className="mt-0.5"
              checked={approved}
              disabled={isLaunching}
              onChange={handleToggleApproval}
              aria-checked={approved}
            />
            <span className="leading-snug">{copy.checkbox}</span>
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
              data-hww-coding-plan={`${prefix}-launch-cta`}
              data-launch-enabled={launchDisabled ? "0" : "1"}
            >
              {isLaunching ? copy.launchBusy : copy.launchCta}
            </button>
            {isLaunching ? null : (
              <button
                type="button"
                onClick={handleReset}
                className="text-[11px] text-white/55 hover:text-white/80"
                data-hww-coding-plan={`${prefix}-reset`}
              >
                {copy.discardPreviewLabel}
              </button>
            )}
          </div>
        </div>
      ) : null}

      {state.phase === "running" ? (
        <div
          className="mt-2 grid gap-1.5 text-[11px] text-white/75"
          data-hww-coding-plan={`${prefix}-running`}
        >
          <p className="leading-snug">{config.runningNote}</p>
          <p className="text-[10px] text-white/50">Checking build status…</p>
        </div>
      ) : null}

      {state.phase === "succeeded" ? (
        <SuccessSummary
          result={state.result}
          onReset={handleReset}
          prefix={prefix}
          copy={copy}
          changedPathsLine={config.changedPathsLine}
        />
      ) : null}

      {state.phase === "failed" ? (
        <div className="mt-2 grid gap-1.5 text-[11px] text-amber-200/90">
          <p data-hww-coding-plan={`${prefix}-error`}>{state.message}</p>
          <div>
            <button
              type="button"
              onClick={handleReset}
              className="rounded-md border border-amber-300/40 bg-amber-300/[0.08] px-2.5 py-1 text-[11px] font-medium text-amber-50 hover:bg-amber-300/[0.12]"
              data-hww-coding-plan={`${prefix}-retry`}
            >
              {copy.startOverLabel}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function SuccessSummary<L extends ManagedProviderBuildLaunchLike>({
  result,
  onReset,
  prefix,
  copy,
  changedPathsLine,
}: {
  result: L;
  onReset: () => void;
  prefix: string;
  copy: ManagedProviderBuildCopy;
  changedPathsLine: (count: number) => string;
}) {
  const snapshotId = readStringField(result.output_ref, "snapshot_id");
  const previewUrl = readStringField(result.output_ref, "preview_url");
  const changedCount = readNumberField(result.output_ref, "changed_paths_count");
  const neutral = readStringField(result.output_ref, "neutral_outcome");
  const changedLine = typeof changedCount === "number" ? changedPathsLine(changedCount) : "";
  const showTechnicalDetails = Boolean(snapshotId || neutral);
  return (
    <div className="mt-2 grid gap-2 text-[11px] text-white/80">
      {previewUrl ? (
        <div
          className="flex flex-wrap items-center gap-x-2 gap-y-1"
          data-hww-coding-plan={`${prefix}-success-actions`}
        >
          <a
            href={previewUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded-md border border-cyan-300/35 bg-cyan-300/[0.08] px-2.5 py-1 text-[11px] font-medium text-cyan-100 hover:bg-cyan-300/[0.14]"
            data-hww-coding-plan={`${prefix}-preview-url`}
          >
            {copy.previewLink}
          </a>
          <a
            href={previewUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="text-[11px] font-medium text-cyan-300/90 underline-offset-2 hover:text-cyan-200 hover:underline"
            data-hww-coding-plan={`${prefix}-view-changes-url`}
          >
            {copy.viewChangesLink}
          </a>
        </div>
      ) : null}
      {changedLine ? (
        <p
          className="text-[10px] leading-snug text-white/55"
          data-hww-coding-plan={`${prefix}-changed-count`}
        >
          {changedLine}
        </p>
      ) : null}
      {showTechnicalDetails ? (
        <details
          className="rounded border border-white/[0.06] bg-white/[0.02] px-2 py-1.5"
          data-hww-coding-plan={`${prefix}-technical-details`}
        >
          <summary className="cursor-pointer select-none text-[10px] font-medium tracking-wide text-white/45 hover:text-white/70">
            {copy.technicalDetailsSummary}
          </summary>
          <ul className="mt-1.5 grid gap-1 text-[10px] text-white/70">
            {snapshotId ? (
              <li data-hww-coding-plan={`${prefix}-snapshot-id`}>
                <span className="text-white/50">{copy.snapshotIdLabel} </span>
                <span className="font-mono text-white/85">{snapshotId}</span>
              </li>
            ) : null}
            {neutral ? (
              <li data-hww-coding-plan={`${prefix}-neutral-outcome`}>
                <span className="text-white/50">{copy.outcomeLabel} </span>
                <span className="font-mono text-white/85">{neutral}</span>
              </li>
            ) : null}
          </ul>
        </details>
      ) : null}
      <p className="text-[10px] leading-snug text-white/50">{copy.noPrNote}</p>
      <div>
        <button
          type="button"
          onClick={onReset}
          className="rounded-md border border-emerald-300/35 bg-emerald-300/[0.08] px-2.5 py-1 text-[11px] font-medium text-emerald-50 hover:bg-emerald-300/[0.14]"
          data-hww-coding-plan={`${prefix}-done`}
        >
          {copy.keepBuildingCta}
        </button>
      </div>
    </div>
  );
}
