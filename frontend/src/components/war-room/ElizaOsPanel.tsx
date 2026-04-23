import * as React from "react";

import { STUB_ELIZA_THOUGHT_LINES } from "./stubs/elizaStub";
import { BrowserTabPanel } from "./BrowserTabPanel";
import type { WarRoomTabId } from "./uplinkConfig";

export interface ElizaOsPanelProps {
  tabId: WarRoomTabId;
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
}

export function ElizaOsPanel({ tabId, embedUrl, onEmbedUrlChange }: ElizaOsPanelProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
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
