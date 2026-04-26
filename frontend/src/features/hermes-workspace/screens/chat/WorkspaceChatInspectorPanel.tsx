/**
 * Right-side Inspector shell (parity with upstream Hermes Workspace). No fake tool/artifact data.
 */
import * as React from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

type WorkspaceChatInspectorPanelProps = {
  onClose: () => void;
  /** e.g. session id for future wiring — display only, no API calls. */
  sessionId: string | null;
};

export function WorkspaceChatInspectorPanel({ onClose, sessionId }: WorkspaceChatInspectorPanelProps) {
  return (
    <aside
      className="hww-inspector flex h-full min-h-0 w-[min(100vw,18rem)] shrink-0 flex-col border-l border-white/[0.08] bg-[#040d14]/95 shadow-[inset_1px_0_0_0_rgba(255,255,255,0.04)] md:relative md:max-w-[18rem]"
      aria-label="Inspector"
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2.5">
        <h2 className="text-[12px] font-semibold uppercase tracking-[0.1em] text-white/70">Inspector</h2>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-white/50 hover:text-white/90"
          onClick={onClose}
          aria-label="Close inspector"
        >
          <X className="h-4 w-4" strokeWidth={1.5} />
        </Button>
      </div>
      <div className="hww-scroll flex min-h-0 flex-1 flex-col overflow-y-auto px-3 py-4 text-[12px] leading-relaxed text-white/50">
        <p className="text-white/60">
          No tool runs, artifacts, or research events are exposed for this Workspace chat session in HAM yet.
        </p>
        <p className="mt-3 text-[11px] text-white/35">
          {sessionId
            ? `Session ${sessionId.slice(0, 8)}… — when the API surfaces inspector payload, it can be wired here without Hermes browser calls.`
            : "Start or select a session to anchor inspector context (UI only for now)."}
        </p>
      </div>
    </aside>
  );
}
