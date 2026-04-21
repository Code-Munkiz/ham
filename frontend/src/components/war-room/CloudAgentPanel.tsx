import * as React from "react";
import { Package, ScrollText } from "lucide-react";

import { fetchCursorAgent, fetchCursorAgentConversation } from "@/lib/ham/api";

import { BrowserTabPanel } from "./BrowserTabPanel";
import { CloudAgentNotConnected } from "./CloudAgentNotConnected";
import { WarRoomTabs } from "./WarRoomTabs";
import { getDefaultWarRoomTab, getWarRoomTabs, type CloudAgentTabId, type WarRoomTabId } from "./uplinkConfig";

export interface CloudAgentPanelProps {
  activeCloudAgentId: string | null;
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
  requestedTabId?: WarRoomTabId;
  requestedTabNonce?: number;
}

export function CloudAgentPanel({
  activeCloudAgentId,
  embedUrl,
  onEmbedUrlChange,
  requestedTabId,
  requestedTabNonce,
}: CloudAgentPanelProps) {
  const [tabId, setTabId] = React.useState<WarRoomTabId>(() => getDefaultWarRoomTab("cloud_agent"));
  const tabs = getWarRoomTabs("cloud_agent");

  const [agentPayload, setAgentPayload] = React.useState<Record<string, unknown> | null>(null);
  const [convPayload, setConvPayload] = React.useState<unknown | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const hasAgent = Boolean(activeCloudAgentId?.trim());

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
      <WarRoomTabs
        tabs={tabs}
        activeId={tabId}
        onSelect={(id) => setTabId(id)}
      />
      <div className="flex-1 overflow-y-auto min-h-0 p-2">{renderCloudTab(tabId as CloudAgentTabId)}</div>
    </div>
  );
}
