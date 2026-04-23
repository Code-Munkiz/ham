import * as React from "react";
import { Package, ScrollText } from "lucide-react";

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
    <p className="text-[10px] text-white/55 leading-snug">
      <span className="font-bold text-white/45 uppercase tracking-wider">{label}: </span>
      <span className="text-white/75">{value}</span>
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
        return <p className="text-[10px] text-white/40 uppercase tracking-widest p-4">Loading agent status…</p>;
      }
      if (err) {
        return <p className="text-[10px] text-amber-500/80 p-4 font-mono">{err}</p>;
      }
      return (
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-2 text-[#00E5FF]">
            <Package className="h-4 w-4" />
            <span className="text-[9px] font-black uppercase tracking-widest">Artifact &amp; PR tracker</span>
          </div>
          <p className="text-[9px] font-bold text-white/35 uppercase tracking-wider">
            Live agent payload (status / source / target). PR and file rows wire here when mapped from API.
          </p>
          <pre className="text-[9px] font-mono text-white/50 overflow-auto max-h-[240px] p-3 border border-white/10 bg-black/60 rounded">
            {JSON.stringify(agentPayload, null, 2)}
          </pre>
        </div>
      );
    }
    if (id === "transcript") {
      if (loading && convPayload === null) {
        return <p className="text-[10px] text-white/40 uppercase tracking-widest p-4">Loading conversation…</p>;
      }
      if (err) {
        return <p className="text-[10px] text-amber-500/80 p-4 font-mono">{err}</p>;
      }
      return (
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-2 text-[#00E5FF]">
            <ScrollText className="h-4 w-4" />
            <span className="text-[9px] font-black uppercase tracking-widest">Transcript</span>
          </div>
          <pre className="text-[9px] font-mono text-white/50 overflow-auto max-h-[280px] p-3 border border-white/10 bg-black/60 rounded">
            {JSON.stringify(convPayload, null, 2)}
          </pre>
        </div>
      );
    }
    if (id === "artifacts" || id === "overview") {
      return (
        <div className="p-4 space-y-2">
          <p className="text-[9px] font-black uppercase tracking-widest text-white/40">
            {id === "artifacts" ? "Artifacts" : "Overview"}
          </p>
          <p className="text-[10px] text-white/35 leading-relaxed">
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
        <p className="shrink-0 px-2 pt-1 pb-1 text-[9px] font-bold text-white/40 uppercase tracking-wider">
          Mission handling:{" "}
          <span className="text-white/60">
            {cloudMissionHandling === "managed" ? "Managed by HAM" : "Direct"}
          </span>
        </p>
      ) : null}
      {isManaged ? (
        <div className="shrink-0 border-b border-white/5 px-2 pb-2 space-y-1.5">
          <p className="text-[9px] font-black uppercase tracking-widest text-[#00E5FF]/80">Managed mission</p>
          {managedPollPending && !managedViewSnapshot && !managedPollError ? (
            <p className="text-[10px] text-white/40">Loading mission status from Cursor…</p>
          ) : null}
          {managedPollError ? (
            <p className="text-[10px] text-amber-500/90 font-mono break-words">Last poll: {managedPollError}</p>
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
            <p className="text-[10px] text-white/35">No summary yet — waiting for data from the Cloud Agent API.</p>
          ) : null}
          {managedViewReview ? (
            <div className="mt-1.5 pt-1.5 border-t border-white/10 space-y-1">
              <p className="text-[8px] font-black uppercase tracking-widest text-white/40">HAM review (rules-based)</p>
              <p className={cn("text-[10px] font-semibold leading-snug", reviewSeverityClass(managedViewReview.severity))}>
                {managedViewReview.headline}
              </p>
              {managedViewReview.details?.trim() ? (
                <p className="text-[9px] text-white/50 leading-relaxed whitespace-pre-wrap">{managedViewReview.details}</p>
              ) : null}
              {managedViewReview.nextStep?.trim() ? (
                <p className="text-[9px] text-white/40 leading-snug">
                  <span className="font-bold text-white/50">Next: </span>
                  {managedViewReview.nextStep}
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
