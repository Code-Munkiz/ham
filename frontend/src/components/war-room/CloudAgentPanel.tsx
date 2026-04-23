import * as React from "react";
import { Loader2, Package, ScrollText } from "lucide-react";

import {
  fetchCursorAgent,
  fetchCursorAgentConversation,
  fetchVercelManagedDeployStatus,
  fetchVercelPostDeployValidation,
  type PostDeployValidationState,
  type VercelManagedDeployState,
  type VercelManagedDeployStatus,
  type VercelPostDeployValidationResponse,
} from "@/lib/ham/api";
import {
  parseCursorConversationToLines,
  type CursorTranscriptLine,
} from "@/lib/ham/cursorConversationTranscript";
import { cn } from "@/lib/utils";
import type { CloudMissionHandling, ManagedReviewSeverity } from "@/lib/ham/types";
import { useManagedCloudAgentContext } from "@/contexts/ManagedCloudAgentContext";

import { buildReadableAgentFields } from "@/lib/ham/cursorAgentTrackerView";

import { BrowserTabPanel } from "./BrowserTabPanel";
import { CloudAgentNotConnected } from "./CloudAgentNotConnected";
import type { CloudAgentTabId, WarRoomTabId } from "./uplinkConfig";

export interface CloudAgentPanelProps {
  /** Active tab (owned by `WarRoomPane` — tab strip is in the execution chrome). */
  tabId: WarRoomTabId;
  activeCloudAgentId: string | null;
  /** Cloud Agent only: how this mission is handled in HAM (UI + future orchestration). */
  cloudMissionHandling?: CloudMissionHandling;
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
}

function reviewSeverityClass(s: ManagedReviewSeverity): string {
  if (s === "error") return "text-rose-400/95";
  if (s === "warning") return "text-amber-400/90";
  if (s === "success") return "text-emerald-400/90";
  return "text-sky-300/85";
}

function vercelDeployStateLabel(s: VercelManagedDeployState): string {
  switch (s) {
    case "not_configured":
      return "Vercel not configured on server";
    case "not_observed":
      return "Deployment not yet observed";
    case "pending":
      return "Deployment pending";
    case "building":
      return "Deployment building";
    case "ready":
      return "Deployment ready";
    case "error":
      return "Deployment failed";
    case "canceled":
      return "Deployment canceled";
    case "unknown":
    default:
      return "Vercel status unknown";
  }
}

function vercelStateAccentClass(s: VercelManagedDeployState): string {
  if (s === "ready") return "text-emerald-400/90";
  if (s === "error") return "text-rose-400/90";
  if (s === "building" || s === "pending") return "text-amber-400/90";
  if (s === "canceled") return "text-white/50";
  if (s === "not_configured" || s === "not_observed" || s === "unknown") return "text-cyan-300/85";
  return "text-white/70";
}

function postDeployValidationLabel(s: PostDeployValidationState): string {
  switch (s) {
    case "passed":
      return "Server-side check passed";
    case "failed":
      return "Server-side check failed";
    case "inconclusive":
      return "Server-side check inconclusive";
    case "pending":
      return "Checking…";
    case "not_attempted":
    default:
      return "Validation not attempted";
  }
}

function postDeployValidationAccentClass(s: PostDeployValidationState): string {
  if (s === "passed") return "text-lime-400/90";
  if (s === "failed") return "text-rose-400/90";
  if (s === "inconclusive") return "text-amber-400/90";
  if (s === "pending") return "text-white/60";
  return "text-amber-200/80";
}

function snapshotLine(label: string, value: string | null | undefined): React.ReactNode {
  if (!value?.trim()) return null;
  return (
    <p className="text-[13px] font-medium leading-[1.6] uppercase tracking-[0.02em] text-white/80">
      <span className="text-white/45 font-bold">{label}: </span>
      {value}
    </p>
  );
}

const SNAPSHOT_PROGRESS_MAX = 420;

function SnapshotProgressField({ value }: { value: string | null | undefined }) {
  const [open, setOpen] = React.useState(false);
  if (!value?.trim()) return null;
  const t = value.trim();
  const tooLong = t.length > SNAPSHOT_PROGRESS_MAX;
  const body = tooLong && !open ? `${t.slice(0, SNAPSHOT_PROGRESS_MAX).trimEnd()}…` : t;
  return (
    <div className="text-[13px] font-medium leading-[1.6] uppercase tracking-[0.02em] text-white/80">
      <span className="text-white/45 font-bold">Progress: </span>
      <span className="whitespace-pre-wrap [overflow-wrap:anywhere]">{body}</span>
      {tooLong ? (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="ml-1.5 align-baseline text-[10px] font-black uppercase tracking-widest text-[#00E5FF] hover:text-white"
        >
          {open ? "Show less" : "Show more"}
        </button>
      ) : null}
    </div>
  );
}

export function CloudAgentPanel({
  tabId,
  activeCloudAgentId,
  cloudMissionHandling = "direct",
  embedUrl,
  onEmbedUrlChange,
}: CloudAgentPanelProps) {
  const managed = useManagedCloudAgentContext();

  const [agentPayload, setAgentPayload] = React.useState<Record<string, unknown> | null>(null);
  const [convPayload, setConvPayload] = React.useState<unknown | null>(null);
  const [transcriptView, setTranscriptView] = React.useState<"readable" | "raw">("readable");
  const [trackerView, setTrackerView] = React.useState<"readable" | "raw">("readable");
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [vercelDeploy, setVercelDeploy] = React.useState<VercelManagedDeployStatus | null>(null);
  const [vercelDeployErr, setVercelDeployErr] = React.useState<string | null>(null);
  const [vercelDeployLoading, setVercelDeployLoading] = React.useState(false);
  const [postDeploy, setPostDeploy] = React.useState<VercelPostDeployValidationResponse | null>(null);
  const [postDeployErr, setPostDeployErr] = React.useState<string | null>(null);
  const [postDeployLoading, setPostDeployLoading] = React.useState(false);
  const [postDeployRecheckBusy, setPostDeployRecheckBusy] = React.useState(false);

  const transcriptLines: CursorTranscriptLine[] = React.useMemo(
    () => parseCursorConversationToLines(convPayload),
    [convPayload],
  );

  const trackerReadable = React.useMemo(
    () => buildReadableAgentFields(agentPayload),
    [agentPayload],
  );

  const hasAgent = Boolean(activeCloudAgentId?.trim());
  const isManaged = cloudMissionHandling === "managed" && hasAgent;
  const managedPollError = isManaged ? managed.pollError : null;
  const managedPollPending = isManaged && managed.pollPending;
  const managedViewSnapshot = isManaged ? managed.lastSnapshot : null;
  const managedViewReview = isManaged ? managed.lastReview : null;
  const deployRead = isManaged ? managed.lastDeployReadiness : null;
  const dState = isManaged ? managed.deployHandoffState : null;
  const dMsg = isManaged ? managed.deployHandoffMessage : null;
  const dHook = isManaged ? managed.deployHookConfigured : null;
  const dHookMap = isManaged ? managed.deployHookVercelMapping : null;
  const dTrigger = isManaged ? managed.triggerManagedDeploy : null;

  /** Tab-scoped fetch (unchanged for Direct; also used in Managed for raw tracker/transcript JSON). */
  React.useEffect(() => {
    setErr(null);
  }, [tabId, activeCloudAgentId]);

  React.useEffect(() => {
    setTranscriptView("readable");
  }, [activeCloudAgentId]);

  React.useEffect(() => {
    setTrackerView("readable");
  }, [activeCloudAgentId]);

  React.useEffect(() => {
    if (!hasAgent || tabId !== "transcript") {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void fetchCursorAgentConversation(activeCloudAgentId!.trim())
      .then((j) => {
        if (!cancelled) setConvPayload(j);
      })
      .catch((e: unknown) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Request failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hasAgent, tabId, activeCloudAgentId]);

  React.useEffect(() => {
    if (!hasAgent || tabId !== "tracker") {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void fetchCursorAgent(activeCloudAgentId!.trim())
      .then((j) => {
        if (!cancelled) setAgentPayload(j);
      })
      .catch((e: unknown) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Request failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hasAgent, tabId, activeCloudAgentId]);

  /** Server-side Vercel deployment truth (Managed → Overview only). */
  React.useEffect(() => {
    if (!isManaged || !activeCloudAgentId?.trim() || tabId !== "overview") {
      return;
    }
    let cancelled = false;
    const id = activeCloudAgentId.trim();
    setVercelDeployLoading(true);
    const run = () => {
      void fetchVercelManagedDeployStatus(id)
        .then((j) => {
          if (!cancelled) {
            setVercelDeploy(j);
            setVercelDeployErr(null);
          }
        })
        .catch((e: unknown) => {
          if (!cancelled) {
            setVercelDeployErr(e instanceof Error ? e.message : "Request failed");
            setVercelDeploy(null);
          }
        })
        .finally(() => {
          if (!cancelled) setVercelDeployLoading(false);
        });
    };
    run();
    const t = window.setInterval(run, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [isManaged, tabId, activeCloudAgentId]);

  /** Post-deploy HTTP validation (Managed → Overview only; separate from Vercel deploy poll). */
  React.useEffect(() => {
    if (!isManaged || !activeCloudAgentId?.trim() || tabId !== "overview") {
      return;
    }
    let cancelled = false;
    const id = activeCloudAgentId.trim();
    let first = true;
    const doFetch = (force: boolean) => {
      if (force) setPostDeployRecheckBusy(true);
      if (first) setPostDeployLoading(true);
      void fetchVercelPostDeployValidation(id, { force })
        .then((j) => {
          if (!cancelled) {
            setPostDeploy(j);
            setPostDeployErr(null);
          }
        })
        .catch((e: unknown) => {
          if (!cancelled) {
            setPostDeployErr(e instanceof Error ? e.message : "Request failed");
            setPostDeploy(null);
          }
        })
        .finally(() => {
          if (!cancelled) {
            first = false;
            setPostDeployLoading(false);
            setPostDeployRecheckBusy(false);
          }
        });
    };
    doFetch(false);
    const t = window.setInterval(() => doFetch(false), 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [isManaged, tabId, activeCloudAgentId]);

  const notConnected = !hasAgent;

  const onPostDeployRecheck = () => {
    if (!isManaged || !activeCloudAgentId?.trim()) return;
    setPostDeployRecheckBusy(true);
    if (!postDeploy) setPostDeployLoading(true);
    void fetchVercelPostDeployValidation(activeCloudAgentId.trim(), { force: true })
      .then((j) => {
        setPostDeploy(j);
        setPostDeployErr(null);
      })
      .catch((e: unknown) => {
        setPostDeployErr(e instanceof Error ? e.message : "Request failed");
        setPostDeploy(null);
      })
      .finally(() => {
        setPostDeployRecheckBusy(false);
        setPostDeployLoading(false);
      });
  };

  function renderCloudTab(id: CloudAgentTabId) {
    if (id === "browser") {
      return <BrowserTabPanel embedUrl={embedUrl} onEmbedUrlChange={onEmbedUrlChange} />;
    }
    if (notConnected) {
      return <CloudAgentNotConnected />;
    }
    if (id === "tracker") {
      if (loading && !agentPayload) {
        return (
          <p className="text-[13px] font-medium text-white/60 uppercase tracking-[0.02em] p-4">Loading agent status…</p>
        );
      }
      if (err) {
        return <p className="text-[13px] text-amber-500/80 p-4 font-mono leading-relaxed">{err}</p>;
      }
      const rawJson = JSON.stringify(agentPayload, null, 2);
      return (
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[#00E5FF]">
            <div className="flex min-w-0 items-center gap-2">
              <Package className="h-5 w-5 shrink-0" />
              <span className="text-[11px] font-black uppercase tracking-widest">Artifact &amp; PR tracker</span>
            </div>
            <button
              type="button"
              onClick={() => setTrackerView((v) => (v === "readable" ? "raw" : "readable"))}
              className="shrink-0 rounded-md border border-white/15 bg-black/50 px-2.5 py-1.5 text-[10px] font-black uppercase tracking-widest text-white/80 hover:border-[#FF6B00]/50 hover:text-[#FF6B00]"
            >
              {trackerView === "readable" ? "Show raw JSON" : "Readable view"}
            </button>
          </div>
          {trackerView === "raw" ? (
            <p className="text-[10px] font-bold text-white/35">
              Raw agent payload from Cursor (via HAM) — for debugging; API shape may change.
            </p>
          ) : (
            <p className="text-[13px] font-medium text-white/70 uppercase tracking-[0.02em] leading-[1.6]">
              Status, repository, and handoff from the live agent object. Structured PR/artifact rows will map here when
              available.
            </p>
          )}
          {trackerView === "raw" ? (
            <pre className="overflow-x-auto rounded border border-white/10 bg-black/60 p-3 text-[12px] font-mono text-white/75 leading-relaxed">
              {rawJson}
            </pre>
          ) : (
            <ul className="space-y-2.5 rounded-xl border border-white/10 bg-black/40 p-3">
              {trackerReadable.map((row, i) => (
                <li key={`${i}-${row.label}`} className="border-b border-white/5 pb-2.5 last:border-0 last:pb-0">
                  <p className="text-[10px] font-black uppercase tracking-widest text-white/40">{row.label}</p>
                  <p className="mt-1 text-[13px] font-medium leading-[1.5] text-white/88 [overflow-wrap:anywhere]">
                    {row.value}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    }
    if (id === "transcript") {
      if (loading && convPayload === null) {
        return (
          <p className="text-[13px] font-medium text-white/60 uppercase tracking-[0.02em] p-4">Loading conversation…</p>
        );
      }
      if (err) {
        return <p className="text-[13px] text-amber-500/80 p-4 font-mono leading-relaxed">{err}</p>;
      }
      const rawJson = JSON.stringify(convPayload, null, 2);
      return (
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[#00E5FF]">
            <div className="flex min-w-0 items-center gap-2">
              <ScrollText className="h-5 w-5 shrink-0" />
              <span className="text-[11px] font-black uppercase tracking-widest">Transcript</span>
            </div>
            <button
              type="button"
              onClick={() => setTranscriptView((v) => (v === "readable" ? "raw" : "readable"))}
              className="shrink-0 rounded-md border border-white/15 bg-black/50 px-2.5 py-1.5 text-[10px] font-black uppercase tracking-widest text-white/80 hover:border-[#FF6B00]/50 hover:text-[#FF6B00]"
            >
              {transcriptView === "readable" ? "Show raw JSON" : "Readable view"}
            </button>
          </div>
          {transcriptView === "raw" ? (
            <p className="shrink-0 text-[10px] font-bold text-white/35">
              Raw payload from Cursor (via HAM) — for debugging; API shape may change.
            </p>
          ) : null}
          {transcriptView === "raw" ? (
            <pre className="overflow-x-auto rounded border border-white/10 bg-black/60 p-3 text-[12px] font-mono text-white/75 leading-relaxed">
              {rawJson}
            </pre>
          ) : transcriptLines.length > 0 ? (
            <ul className="space-y-3 pr-0.5">
              {transcriptLines.map((l) => {
                const label =
                  l.role === "user"
                    ? "You"
                    : l.role === "assistant"
                      ? "Cloud agent"
                      : l.role === "system"
                        ? "Tool / system"
                        : "Message";
                return (
                  <li
                    key={l.id}
                    className={cn(
                      "rounded-xl border p-3",
                      l.role === "user"
                        ? "border-white/10 bg-white/[0.04]"
                        : l.role === "assistant"
                          ? "border-[#FF6B00]/30 bg-[#FF6B00]/[0.05]"
                          : l.role === "system"
                            ? "border-amber-500/20 bg-amber-500/5"
                            : "border-white/10 bg-white/[0.02]",
                    )}
                  >
                    <p className="text-[10px] font-black uppercase tracking-widest text-white/40">{label}</p>
                    <p className="mt-2 text-[13px] font-medium leading-[1.6] text-white/90 whitespace-pre-wrap [overflow-wrap:anywhere]">
                      {l.body}
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="min-h-0 flex-1 space-y-2 rounded-xl border border-dashed border-white/15 bg-black/30 p-4">
              <p className="text-[13px] font-medium leading-[1.5] text-white/60">
                No chat lines were parsed from this response (Cursor may use a new JSON shape). Open{" "}
                <button
                  type="button"
                  onClick={() => setTranscriptView("raw")}
                  className="font-bold text-[#00E5FF] underline decoration-[#00E5FF]/40 underline-offset-2 hover:text-white"
                >
                  raw JSON
                </button>{" "}
                to inspect the payload.
              </p>
            </div>
          )}
        </div>
      );
    }
    if (id === "artifacts") {
      return (
        <div className="space-y-2 p-4">
          <p className="text-[11px] font-black uppercase tracking-widest text-white/50">Artifacts</p>
          <p className="text-[13px] font-medium uppercase leading-[1.6] tracking-[0.02em] text-white/70">
            Structured artifact list and checks will map from Cloud Agent API responses. No stub rows.
          </p>
        </div>
      );
    }
    if (id === "overview") {
      return (
        <div className="space-y-3 p-4">
          <div>
            <p className="text-[11px] font-black uppercase tracking-widest text-white/50">Overview</p>
            <p className="mt-1 text-[10px] font-medium leading-snug text-white/32">
              Mission-wide context (poll summary, rules-based review, deploy handoff). Tab-specific data lives in Tracker,
              Transcript, and Browser.
            </p>
          </div>
          {hasAgent ? (
            <p className="text-[12px] font-bold uppercase tracking-wider text-white/45">
              Mission handling:{" "}
              <span className="text-white/75">
                {cloudMissionHandling === "managed" ? "Managed by HAM" : "Direct"}
              </span>
            </p>
          ) : null}
          {isManaged ? (
            <div className="space-y-1.5 border-t border-white/10 pt-3">
              {vercelDeploy?.vercel_mapping || dHookMap ? (
                <div className="mb-1 space-y-1 rounded-md border border-white/10 bg-black/30 px-2.5 py-2">
                  <p className="text-[9px] font-black uppercase tracking-widest text-white/40">Vercel mapping (server)</p>
                  {vercelDeploy?.vercel_mapping ? (
                    <p className="text-[12px] leading-[1.5] text-white/55">
                      <span className="text-white/40">Project list: </span>
                      {vercelDeploy.vercel_mapping.message}
                      {vercelDeploy.vercel_mapping.project_id_used ? (
                        <span className="ml-1 font-mono text-[11px] text-white/50">
                          ({vercelDeploy.vercel_mapping.project_id_used}
                          {vercelDeploy.vercel_mapping.team_id_used
                            ? `, team: ${vercelDeploy.vercel_mapping.team_id_used}`
                            : ""}
                          )
                        </span>
                      ) : null}
                    </p>
                  ) : null}
                  {vercelDeploy?.vercel_mapping?.repo_key ? (
                    <p className="text-[10px] font-mono text-white/35">repo: {vercelDeploy.vercel_mapping.repo_key}</p>
                  ) : null}
                  {dHookMap ? (
                    <p className="text-[12px] leading-[1.5] text-white/55">
                      <span className="text-white/40">Deploy hook: </span>
                      {dHookMap.message}
                    </p>
                  ) : null}
                  {dHookMap?.used_global_hook_fallback ? (
                    <p className="text-[10px] text-amber-400/80">Global deploy hook fallback was used (policy).</p>
                  ) : null}
                  {vercelDeploy?.vercel_mapping?.map_load_error || dHookMap?.map_load_error ? (
                    <p className="text-[10px] text-rose-400/80 font-mono">
                      Map load: {vercelDeploy?.vercel_mapping?.map_load_error || dHookMap?.map_load_error}
                    </p>
                  ) : null}
                </div>
              ) : null}
              <p className="text-[11px] font-black uppercase tracking-widest text-[#00E5FF]/85">Managed mission</p>
              <p className="text-[10px] font-medium leading-snug text-white/32">
                Live summary from HAM&rsquo;s Cursor API poll&mdash;rules-based review and deploy notes below. Use
                Transcript and Tracker for the full payloads.
              </p>
              {managedPollPending && !managedViewSnapshot && !managedPollError ? (
                <p className="text-[13px] font-medium text-white/50 uppercase tracking-[0.02em] leading-[1.6]">
                  Loading mission status from Cursor…
                </p>
              ) : null}
              {managedPollError ? (
                <p className="text-[13px] text-amber-500/90 font-mono break-words leading-relaxed">
                  Last poll: {managedPollError}
                </p>
              ) : null}
              {managedViewSnapshot ? (
                <div className="space-y-0.5">
                  {snapshotLine("Status", managedViewSnapshot.status)}
                  <SnapshotProgressField value={managedViewSnapshot.progress} />
                  {snapshotLine("Blocker", managedViewSnapshot.blocker)}
                  {snapshotLine("Branch / PR", managedViewSnapshot.branchOrPr)}
                  {snapshotLine("Updated", managedViewSnapshot.updatedAt)}
                </div>
              ) : !managedPollPending && !managedPollError ? (
                <p className="text-[13px] font-medium text-white/50 uppercase tracking-[0.02em] leading-[1.6]">
                  No summary yet — waiting for data from the Cloud Agent API.
                </p>
              ) : null}
              {managedViewReview ? (
                <div className="mt-1.5 space-y-1 border-t border-white/10 pt-3">
                  <p className="text-[10px] font-black uppercase tracking-widest text-white/45">HAM review (rules-based)</p>
                  <p
                    className={cn(
                      "text-[13px] font-semibold leading-[1.5]",
                      reviewSeverityClass(managedViewReview.severity),
                    )}
                  >
                    {managedViewReview.headline}
                  </p>
                  {managedViewReview.details?.trim() ? (
                    <p className="text-[13px] font-medium leading-[1.6] text-white/65 whitespace-pre-wrap">
                      {managedViewReview.details}
                    </p>
                  ) : null}
                  {managedViewReview.nextStep?.trim() ? (
                    <p className="text-[12px] leading-[1.5] text-white/55">
                      <span className="font-bold text-white/65">Next: </span>
                      {managedViewReview.nextStep}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {deployRead ? (
                <div className="mt-1.5 space-y-1.5 border-t border-white/10 pt-3">
                  <p className="text-[10px] font-black uppercase tracking-widest text-violet-400/85">
                    Deploy handoff (Vercel hook)
                  </p>
                  <p className={cn("text-[13px] font-semibold leading-[1.5]", reviewSeverityClass(deployRead.severity))}>
                    {deployRead.headline}
                  </p>
                  {deployRead.details?.trim() ? (
                    <p className="text-[13px] font-medium leading-[1.6] text-white/65 whitespace-pre-wrap">
                      {deployRead.details}
                    </p>
                  ) : null}
                  {deployRead.nextStep?.trim() ? (
                    <p className="text-[12px] leading-[1.5] text-white/55">
                      <span className="font-bold text-white/65">Next: </span>
                      {deployRead.nextStep}
                    </p>
                  ) : null}
                  {dHook === null ? (
                    <p className="text-[13px] font-medium text-white/45">Checking deploy hook configuration…</p>
                  ) : dHook === false ? (
                    <p className="text-[13px] font-medium leading-[1.5] text-amber-500/85">
                      Deploy hook is not configured on the API (set{" "}
                      <span className="font-mono">HAM_VERCEL_DEPLOY_HOOK_URL</span>).
                    </p>
                  ) : null}
                  {dState === "hook_accepted" && dMsg ? (
                    <p className="text-[13px] border border-white/10 bg-black/40 leading-[1.5] text-emerald-400/90 rounded px-2 py-1.5">
                      {dMsg}
                    </p>
                  ) : null}
                  {dState === "hook_failed" && dMsg ? (
                    <p className="text-[13px] border border-amber-500/20 bg-black/40 leading-[1.5] text-amber-500/90 rounded px-2 py-1.5">
                      {dMsg}
                    </p>
                  ) : null}
                  {dState === "ready" && dTrigger && dHook === true ? (
                    <button
                      type="button"
                      className="mt-0.5 w-full rounded border border-violet-500/40 bg-violet-500/10 px-2 py-2 text-left text-[12px] font-black uppercase tracking-widest text-violet-300 hover:bg-violet-500/20"
                      onClick={() => {
                        void dTrigger();
                      }}
                    >
                      Trigger Vercel deploy hook
                    </button>
                  ) : null}
                  {dState === "triggering" ? (
                    <p className="flex items-center gap-2 text-[13px] text-white/55">
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                      Requesting deploy hook…
                    </p>
                  ) : null}
                </div>
              ) : null}
              <div className="mt-1.5 space-y-1.5 border-t border-white/10 pt-3">
                <p className="text-[10px] font-black uppercase tracking-widest text-teal-300/85">
                  Vercel deployment (server poll)
                </p>
                <p className="text-[10px] font-medium leading-snug text-white/32">
                  Observed from the Vercel Deployments API on the HAM host — not the same as the deploy hook button above.
                </p>
                {vercelDeployLoading && !vercelDeploy && !vercelDeployErr ? (
                  <p className="flex items-center gap-2 text-[13px] text-white/55">
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                    Loading Vercel deployment status…
                  </p>
                ) : null}
                {vercelDeployErr ? (
                  <p className="text-[13px] text-amber-500/90 font-mono break-words leading-relaxed">{vercelDeployErr}</p>
                ) : null}
                {vercelDeploy ? (
                  <div className="space-y-1.5">
                    <p className={cn("text-[13px] font-semibold leading-[1.5]", vercelStateAccentClass(vercelDeploy.state))}>
                      {vercelDeployStateLabel(vercelDeploy.state)}
                    </p>
                    {vercelDeploy.match_confidence ? (
                      <p className="text-[12px] text-white/50">
                        Match confidence: <span className="font-mono text-white/70">{vercelDeploy.match_confidence}</span>
                        {vercelDeploy.match_reason ? (
                          <span className="text-white/40"> — {vercelDeploy.match_reason}</span>
                        ) : null}
                      </p>
                    ) : null}
                    <p className="text-[13px] font-medium leading-[1.6] text-white/65 whitespace-pre-wrap">
                      {vercelDeploy.message}
                    </p>
                    {vercelDeploy.deployment?.url?.trim() ? (
                      <a
                        href={vercelDeploy.deployment.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-block text-[12px] font-bold text-[#00E5FF] underline decoration-[#00E5FF]/40 underline-offset-2 hover:text-white break-all"
                      >
                        {vercelDeploy.deployment.url}
                      </a>
                    ) : null}
                    <p className="text-[10px] text-white/35 font-mono">
                      Last checked: {vercelDeploy.checked_at}
                    </p>
                    {vercelDeploy.state === "not_configured" ? (
                      <p className="text-[12px] text-white/45 leading-[1.5]">
                        Configure <span className="font-mono">HAM_VERCEL_API_TOKEN</span> (or{" "}
                        <span className="font-mono">VERCEL_API_TOKEN</span>) and{" "}
                        <span className="font-mono">HAM_VERCEL_PROJECT_ID</span> (or <span className="font-mono">VERCEL_PROJECT_ID</span>
                        ) on the API. Optional: <span className="font-mono">HAM_VERCEL_TEAM_ID</span>.
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <div className="mt-1.5 space-y-1.5 border-t border-amber-500/20 pt-3">
                <p className="text-[10px] font-black uppercase tracking-widest text-amber-400/90">
                  Post-deploy validation (server check)
                </p>
                <p className="text-[10px] font-medium leading-snug text-white/32">
                  Bounded HTTP check against the <span className="text-white/50">same deployment URL</span> as Vercel
                  match above &mdash; not a browser, not E2E, and not the deploy hook.
                </p>
                {postDeployLoading && !postDeploy && !postDeployErr ? (
                  <p className="flex items-center gap-2 text-[13px] text-white/55">
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                    Loading post-deploy validation…
                  </p>
                ) : null}
                {postDeployErr ? (
                  <p className="text-[13px] text-amber-500/90 font-mono break-words leading-relaxed">{postDeployErr}</p>
                ) : null}
                {postDeploy ? (
                  <div className="space-y-1.5">
                    <p
                      className={cn(
                        "text-[13px] font-semibold leading-[1.5]",
                        postDeployValidationAccentClass(postDeploy.post_deploy_validation.state),
                      )}
                    >
                      {postDeployValidationLabel(postDeploy.post_deploy_validation.state)}
                    </p>
                    <p className="text-[12px] text-white/50">
                      Reason:{" "}
                      <span className="font-mono text-white/70">
                        {postDeploy.post_deploy_validation.reason_code ?? "—"}
                      </span>
                    </p>
                    <p className="text-[13px] font-medium leading-[1.6] text-white/65 whitespace-pre-wrap">
                      {postDeploy.post_deploy_validation.message}
                    </p>
                    {postDeploy.post_deploy_validation.url_probed?.trim() ? (
                      <p className="text-[10px] text-white/50 break-all font-mono">
                        <span className="text-white/35">Probed: </span>
                        {postDeploy.post_deploy_validation.url_probed}
                      </p>
                    ) : null}
                    {postDeploy.post_deploy_validation.http_status ? (
                      <p className="text-[10px] text-white/40 font-mono">
                        HTTP {postDeploy.post_deploy_validation.http_status}
                        {postDeploy.post_deploy_validation.final_url &&
                        postDeploy.post_deploy_validation.final_url !== postDeploy.post_deploy_validation.url_probed
                          ? ` — final: ${postDeploy.post_deploy_validation.final_url}`
                          : null}
                      </p>
                    ) : null}
                    <p className="text-[10px] text-white/35 font-mono">Checked: {postDeploy.post_deploy_validation.checked_at}</p>
                    <button
                      type="button"
                      onClick={onPostDeployRecheck}
                      disabled={postDeployRecheckBusy}
                      className="mt-0.5 w-full rounded border border-amber-500/30 bg-amber-500/5 px-2 py-2 text-left text-[11px] font-black uppercase tracking-widest text-amber-200/90 hover:bg-amber-500/15 disabled:opacity-50"
                    >
                      {postDeployRecheckBusy ? "Re-checking (force)…" : "Re-check with force (any match confidence)"}
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          ) : hasAgent ? (
            <p className="text-[13px] font-medium leading-[1.6] text-white/55">
              Direct mode: use Tracker and Transcript for live Cursor API payloads.
            </p>
          ) : null}
        </div>
      );
    }
    return <CloudAgentNotConnected />;
  }

  const compactManagedStatus =
    isManaged && tabId !== "overview"
      ? managedPollPending && !managedViewSnapshot?.status?.trim()
        ? "…"
        : managedViewSnapshot?.status?.trim() || "—"
      : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {compactManagedStatus !== null ? (
        <p
          className="shrink-0 border-b border-white/5 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-white/40"
          title="Open Overview for full mission context"
        >
          Managed · <span className="text-white/65">{compactManagedStatus}</span>
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto p-2">{renderCloudTab(tabId as CloudAgentTabId)}</div>
    </div>
  );
}
