import * as React from "react";

import { cn } from "@/lib/utils";
import { STUB_SWARM_WORKERS } from "./stubs/factoryAiStub";
import { BrowserTabPanel } from "./BrowserTabPanel";
import type { WarRoomTabId } from "./uplinkConfig";

export interface FactoryAIPanelProps {
  tabId: WarRoomTabId;
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
}

export function FactoryAIPanel({ tabId, embedUrl, onEmbedUrlChange }: FactoryAIPanelProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className={cn("min-h-0 flex-1 flex flex-col", tabId === "browser" ? "p-1.5" : "overflow-y-auto p-2")}>
        {tabId === "browser" ? (
          <BrowserTabPanel embedUrl={embedUrl} onEmbedUrlChange={onEmbedUrlChange} />
        ) : tabId === "swarm" ? (
          <div className="p-4 space-y-4">
            <p className="text-[9px] font-black uppercase tracking-widest text-[#BC13FE]">Swarm status grid</p>
            <p className="text-[9px] font-bold text-white/30 uppercase">
              Stub view model — replace with live workforce API when available.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {STUB_SWARM_WORKERS.map((w) => (
                <div key={w.id} className="border border-[#BC13FE]/30 bg-black/50 p-3 space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-[9px] font-black text-[#BC13FE] uppercase">{w.id}</span>
                    <span className="text-[8px] text-white/40">{w.status}</span>
                  </div>
                  <div className="h-1.5 bg-white/10 overflow-hidden">
                    <div
                      className="h-full bg-[#BC13FE]/70"
                      style={{ width: `${w.progressPct}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="p-4 space-y-2">
            <p className="text-[9px] font-black uppercase tracking-widest text-white/40">
              {tabId === "workers" ? "Workers" : "Queue"}
            </p>
            <p className="text-[10px] text-white/30 leading-relaxed">
              Placeholder — no live Factory AI transport yet. Structure preserved for backend drop-in.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
