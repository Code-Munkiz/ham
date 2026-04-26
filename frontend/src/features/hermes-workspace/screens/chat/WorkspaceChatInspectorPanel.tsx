/**
 * Upstream `inspector-panel.tsx` structure: header, tab bar, scroll body — honest empty / unavailable
 * per tab. No zustand in HAM; keep local tab state. No fake tool/artifact/memory rows.
 */
import * as React from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type TabId = "activity" | "artifacts" | "files" | "memory" | "skills" | "logs";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "activity", label: "Activity" },
  { id: "artifacts", label: "Artifacts" },
  { id: "files", label: "Files" },
  { id: "memory", label: "Memory" },
  { id: "skills", label: "Skills" },
  { id: "logs", label: "Logs" },
];

type WorkspaceChatInspectorPanelProps = {
  onClose: () => void;
  sessionId: string | null;
};

const TAB_COPY: Record<TabId, string> = {
  activity: "No activity available yet",
  artifacts: "Artifacts are not wired for Workspace chat yet",
  files: "Files are available through the Files workspace, not live Inspector yet",
  memory: "Memory Inspector is not wired yet",
  skills: "Skills Inspector is not wired yet",
  logs: "Logs are not available for this session yet",
};

function TabEmpty({ tabId, sessionId }: { tabId: TabId; sessionId: string | null }) {
  return (
    <div className="p-3">
      <p className="text-[12px] leading-relaxed text-white/60">{TAB_COPY[tabId]}</p>
      {tabId === "activity" && sessionId ? (
        <p className="mt-2 text-[11px] text-white/30">
          Session {sessionId.slice(0, 8)}… — inspector payload can be wired when available (no Hermes
          browser calls).
        </p>
      ) : null}
    </div>
  );
}

export function WorkspaceChatInspectorPanel({ onClose, sessionId }: WorkspaceChatInspectorPanelProps) {
  const [activeTab, setActiveTab] = React.useState<TabId>("activity");

  return (
    <aside
      className={cn(
        "hww-inspector flex h-full min-h-0 w-[min(100vw,22rem)] shrink-0 flex-col overflow-hidden",
        "border-l border-white/[0.08] bg-[#040d14]/95 shadow-[inset_1px_0_0_0_rgba(255,255,255,0.04)]",
        "md:w-[min(100vw,350px)]",
      )}
      style={{
        boxShadow: "-4px 0 16px rgba(0, 0, 0, 0.2)",
      }}
      aria-label="Inspector"
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/[0.08] px-3 py-2.5">
        <h2 className="text-sm font-semibold text-white/90">Inspector</h2>
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

      <div className="flex shrink-0 gap-0 overflow-x-auto border-b border-white/[0.08]">
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                setActiveTab(tab.id);
              }}
              className={cn(
                "shrink-0 px-2.5 py-2.5 text-[11px] font-medium transition-colors",
                active ? "border-b-2 text-[#ffb27a]" : "border-b-2 border-transparent text-white/45 hover:text-white/75",
              )}
              style={
                active
                  ? { borderBottomColor: "rgba(196, 92, 18, 0.8)" }
                  : { borderBottomColor: "transparent" }
              }
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="hww-scroll min-h-0 flex-1 overflow-y-auto">
        <TabEmpty tabId={activeTab} sessionId={sessionId} />
      </div>
    </aside>
  );
}
