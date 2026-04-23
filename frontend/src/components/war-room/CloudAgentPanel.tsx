import * as React from "react";
import { Loader2, Package, ScrollText } from "lucide-react";

import { fetchCursorAgent, fetchCursorAgentConversation } from "@/lib/ham/api";
import { cn } from "@/lib/utils";
import type { CloudMissionHandling, ManagedReviewSeverity } from "@/lib/ham/types";
import { useManagedCloudAgentContext } from "@/contexts/ManagedCloudAgentContext";

import { BrowserTabPanel } from "./BrowserTabPanel";
import { CloudAgentNotConnected } from "./CloudAgentNotConnected";
import { WarRoomTabs } from "./WarRoomTabs";
import { getDefaultWarRoomTab, getWarRoomTabs, type CloudAgentTabId, type WarRoomTabId } from "./uplinkConfig";

export interface CloudAgentPanelProps {
  activeCloudAgentId: string | null;
  /** Cloud Agent only: how this mission is handled in HAM (UI + future orchestration). */
  cloudMissionHandling?: CloudMissionHandling;
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
  requestedTabId?: WarRoomTabId;
  requestedTabNonce?: number;
}

function reviewSeverityClass(s: ManagedReviewSeverity): string {
  if (s === "error") return "text-rose-400/95";
  if (s === "warning") return "text-amber-400/90";
  if (s === "success") return "text-emerald-400/90";
  return "text-sky-300/85";
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

export function CloudAgentPanel({
  activeCloudAgentId,
  cloudMissionHandling = "direct",
  embedUrl,
  onEmbedUrlChange,
  requestedTabId,
  requestedTabNonce,
}: CloudAgentPanelProps) {
  const [tabId, setTabId] = React.useState<WarRoomTabId>(() => getDefaultWarRoomTab("cloud_agent"));
  const tabs = getWarRoomTabs("cloud_agent");
  const managed = useManagedCloudAgentContext();

  const [agentPayload, setAgentPayload] = React.useState<Record<string, unknown> | null>(null);
  const [convPayload, setConvPayload] = React.useState<unknown | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

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
  const dTrigger = isManaged ? managed.triggerManagedDeploy : null;

  /** Tab-scoped fetch (unchanged for Direct; also used in Managed for raw tracker/transcript JSON). */
  React.useEffect(() => {
    setErr(null);
  }, [tabId, activeCloudAgentId]);

  React.useEffect(() => {
    if (!requestedTabId || !tabs.some((t) => t.id === requestedTabId)) return;
    setTabId(requestedTabId);
  }, [requestedTabId, requestedTabNonce, tabs]);

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

  const notConnected = !hasAgent;

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
      return (
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-2 text-[#00E5FF]">
            <Package className="h-5 w-5 shrink-0" />
            <span className="text-[11px] font-black uppercase tracking-widest">Artifact &amp; PR tracker</span>
          </div>
          <p className="text-[13px] font-medium text-white/70 uppercase tracking-[0.02em] leading-[1.6]">
            Live agent payload (status / source / target). PR and file rows wire here when mapped from API.
          </p>
          <pre className="text-[12px] font-mono text-white/70 overflow-auto max-h-[240px] p-3 border border-white/10 bg-black/60 rounded leading-relaxed">
            {JSON.stringify(agentPayload, null, 2)}
          </pre>
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
      return (
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-2 text-[#00E5FF]">
            <ScrollText className="h-5 w-5 shrink-0" />
            <span className="text-[11px] font-black uppercase tracking-widest">Transcript</span>
          </div>
          <pre className="text-[12px] font-mono text-white/70 overflow-auto max-h-[280px] p-3 border border-white/10 bg-black/60 rounded leading-relaxed">
            {JSON.stringify(convPayload, null, 2)}
          </pre>
        </div>
      );
    }
    if (id === "artifacts" || id === "overview") {
      return (
        <div className="p-4 space-y-2">
          <p className="text-[11px] font-black uppercase tracking-widest text-white/50">
            {id === "artifacts" ? "Artifacts" : "Overview"}
          </p>
          <p className="text-[13px] font-medium text-white/70 uppercase tracking-[0.02em] leading-[1.6]">
            Structured artifact list and checks will map from Cloud Agent API responses. No stub rows.
          </p>
        </div>
      );
    }
    return <CloudAgentNotConnected />;
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {hasAgent ? (
        <p className="shrink-0 px-2 pt-1 pb-1 text-[12px] font-bold text-white/45 uppercase tracking-wider">
          Mission handling:{" "}
          <span className="text-white/75">
            {cloudMissionHandling === "managed" ? "Managed by HAM" : "Direct"}
          </span>
        </p>
      ) : null}
      {isManaged ? (
        <div className="shrink-0 border-b border-white/5 px-2 pb-2 space-y-1.5">
          <p className="text-[11px] font-black uppercase tracking-widest text-[#00E5FF]/85">Managed mission</p>
          {managedPollPending && !managedViewSnapshot && !managedPollError ? (
            <p className="text-[13px] font-medium text-white/50 uppercase tracking-[0.02em] leading-[1.6]">
              Loading mission status from Cursor…
            </p>
          ) : null}
          {managedPollError ? (
            <p className="text-[13px] text-amber-500/90 font-mono break-words leading-relaxed">Last poll: {managedPollError}</p>
          ) : null}
          {managedViewSnapshot ? (
            <div className="space-y-0.5">
              {snapshotLine("Status", managedViewSnapshot.status)}
              {snapshotLine("Progress", managedViewSnapshot.progress)}
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
            <div className="mt-1.5 pt-1.5 border-t border-white/10 space-y-1">
              <p className="text-[10px] font-black uppercase tracking-widest text-white/45">HAM review (rules-based)</p>
              <p className={cn("text-[13px] font-semibold leading-[1.5]", reviewSeverityClass(managedViewReview.severity))}>
                {managedViewReview.headline}
              </p>
              {managedViewReview.details?.trim() ? (
                <p className="text-[13px] text-white/65 leading-[1.6] whitespace-pre-wrap font-medium">
                  {managedViewReview.details}
                </p>
              ) : null}
              {managedViewReview.nextStep?.trim() ? (
                <p className="text-[12px] text-white/55 leading-[1.5]">
                  <span className="font-bold text-white/65">Next: </span>
                  {managedViewReview.nextStep}
                </p>
              ) : null}
            </div>
          ) : null}
          {deployRead ? (
            <div className="mt-1.5 pt-1.5 border-t border-white/10 space-y-1.5">
              <p className="text-[10px] font-black uppercase tracking-widest text-violet-400/85">
                Deploy handoff (Vercel hook)
              </p>
              <p className={cn("text-[13px] font-semibold leading-[1.5]", reviewSeverityClass(deployRead.severity))}>
                {deployRead.headline}
              </p>
              {deployRead.details?.trim() ? (
                <p className="text-[13px] text-white/65 leading-[1.6] whitespace-pre-wrap font-medium">
                  {deployRead.details}
                </p>
              ) : null}
              {deployRead.nextStep?.trim() ? (
                <p className="text-[12px] text-white/55 leading-[1.5]">
                  <span className="font-bold text-white/65">Next: </span>
                  {deployRead.nextStep}
                </p>
              ) : null}
              {(deployRead.prUrl || deployRead.branch || deployRead.repo) && (
                <div className="text-[12px] text-white/50 space-y-0.5 font-mono break-all leading-relaxed">
                  {deployRead.repo ? <p>Repo: {deployRead.repo}</p> : null}
                  {deployRead.prUrl ? <p>PR/URL: {deployRead.prUrl}</p> : null}
                  {deployRead.branch && !deployRead.prUrl ? <p>Branch: {deployRead.branch}</p> : null}
                </div>
              )}
              {dHook === null ? (
                <p className="text-[13px] font-medium text-white/45">Checking deploy hook configuration…</p>
              ) : dHook === false ? (
                <p className="text-[13px] font-medium text-amber-500/85 leading-[1.5]">
                  Deploy hook is not configured on the API (set <span className="font-mono">HAM_VERCEL_DEPLOY_HOOK_URL</span>).
                </p>
              ) : null}
              {dState === "hook_accepted" && dMsg ? (
                <p className="text-[13px] text-emerald-400/90 border border-white/10 rounded px-2 py-1.5 bg-black/40 leading-[1.5]">
                  {dMsg}
                </p>
              ) : null}
              {dState === "hook_failed" && dMsg ? (
                <p className="text-[13px] text-amber-500/90 border border-amber-500/20 rounded px-2 py-1.5 bg-black/40 leading-[1.5]">
                  {dMsg}
                </p>
              ) : null}
              {dState === "ready" && dTrigger && dHook === true ? (
                <button
                  type="button"
                  className="mt-0.5 w-full text-left text-[12px] font-black uppercase tracking-widest text-violet-300 border border-violet-500/40 bg-violet-500/10 hover:bg-violet-500/20 py-2 px-2 rounded"
                  onClick={() => {
                    void dTrigger();
                  }}
                >
                  Trigger Vercel deploy hook
                </button>
              ) : null}
              {dState === "triggering" ? (
                <p className="text-[13px] text-white/55 flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                  Requesting deploy hook…
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      <WarRoomTabs
        tabs={tabs}
        activeId={tabId}
        onSelect={(id) => setTabId(id)}
      />
      <div className="flex-1 overflow-y-auto min-h-0 p-2">{renderCloudTab(tabId as CloudAgentTabId)}</div>
    </div>
  );
}
