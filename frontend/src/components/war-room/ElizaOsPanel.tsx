import * as React from "react";

import { STUB_ELIZA_THOUGHT_LINES } from "./stubs/elizaStub";
import { BrowserTabPanel } from "./BrowserTabPanel";
import { WarRoomTabs } from "./WarRoomTabs";
import { getDefaultWarRoomTab, getWarRoomTabs, type WarRoomTabId } from "./uplinkConfig";

export interface ElizaOsPanelProps {
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
  requestedTabId?: WarRoomTabId;
  requestedTabNonce?: number;
}

export function ElizaOsPanel({
  embedUrl,
  onEmbedUrlChange,
  requestedTabId,
  requestedTabNonce,
}: ElizaOsPanelProps) {
  const [tabId, setTabId] = React.useState<WarRoomTabId>(() => getDefaultWarRoomTab("eliza_os"));
  const tabs = getWarRoomTabs("eliza_os");

  React.useEffect(() => {
    if (!requestedTabId || !tabs.some((t) => t.id === requestedTabId)) return;
    setTabId(requestedTabId);
  }, [requestedTabId, requestedTabNonce, tabs]);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <WarRoomTabs tabs={tabs} activeId={tabId} onSelect={setTabId} />
      <div className="flex-1 overflow-y-auto min-h-0 p-2">
        {tabId === "browser" ? (
          <BrowserTabPanel embedUrl={embedUrl} onEmbedUrlChange={onEmbedUrlChange} />
        ) : tabId === "thought_stream" ? (
          <div className="border border-[#FF2BD6]/30 bg-black/50 p-4 space-y-2 font-mono">
            <p className="text-[9px] font-black uppercase tracking-widest text-[#FF2BD6] mb-3">Thought stream</p>
            {STUB_ELIZA_THOUGHT_LINES.map((line, i) => (
              <p key={i} className="text-[10px] text-[#FF2BD6]/80 uppercase tracking-tight">
                {line}
              </p>
            ))}
          </div>
        ) : tabId === "context" || tabId === "trace" ? (
          <div className="p-4 space-y-2">
            <p className="text-[9px] font-black uppercase tracking-widest text-white/40">
              {tabId === "context" ? "Context" : "Trace"}
            </p>
            <p className="text-[10px] text-white/30 leading-relaxed">
              Placeholder — ELIZA_OS transport not wired. Presentation shell only.
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
