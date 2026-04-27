/**
 * Upstream `inspector-panel.tsx` structure: header, tab bar, scroll body — honest empty / unavailable
 * per tab. Activity + Logs are wired from real HAM chat stream / session load events only.
 */
import * as React from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { WorkspaceInspectorEvent } from "./workspaceInspectorEvents";

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
  events: WorkspaceInspectorEvent[];
};

const TAB_COPY: Record<Exclude<TabId, "activity" | "logs">, string> = {
  artifacts: "Artifacts are not wired for Workspace chat yet",
  files: "Files are available through the Files workspace, not live Inspector yet",
  memory: "Memory Inspector is not wired yet",
  skills: "Skills Inspector is not wired yet",
};

function formatClock(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusBadgeClass(status: WorkspaceInspectorEvent["status"]): string {
  switch (status) {
    case "error":
      return "bg-red-500/15 text-red-200/90";
    case "warning":
      return "bg-amber-500/15 text-amber-200/90";
    case "info":
      return "bg-sky-500/10 text-sky-200/85";
    default:
      return "bg-emerald-500/10 text-emerald-200/85";
  }
}

function ActivityBody({ events }: { events: WorkspaceInspectorEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/60">
          No activity yet. Start a conversation to populate this timeline.
        </p>
      </div>
    );
  }
  return (
    <ul className="divide-y divide-white/[0.06]">
      {events.map((e) => (
        <li key={e.id} className="px-3 py-2.5">
          <div className="flex items-start justify-between gap-2">
            <p className="min-w-0 flex-1 text-[12px] leading-snug text-white/[0.88]">{e.summary}</p>
            <span
              className={cn(
                "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide",
                statusBadgeClass(e.status),
              )}
            >
              {e.status}
            </span>
          </div>
          <p className="mt-1 font-mono text-[10px] text-white/35">
            {formatClock(e.atIso)}
            {typeof e.meta?.session_id === "string" ? ` · ${String(e.meta.session_id).slice(0, 12)}…` : null}
            {typeof e.meta?.message_id === "string" ? ` · msg ${String(e.meta.message_id).slice(0, 10)}…` : null}
          </p>
        </li>
      ))}
    </ul>
  );
}

function LogsBody({ events }: { events: WorkspaceInspectorEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/60">
          No logs yet. Runtime events will appear after a chat turn.
        </p>
      </div>
    );
  }
  return (
    <ul className="space-y-2 p-3">
      {events.map((e) => {
        const meta =
          e.meta && Object.keys(e.meta).length > 0
            ? JSON.stringify(e.meta, null, 0).replace(/","/g, '", "')
            : "—";
        return (
          <li
            key={e.id}
            className="rounded-md border border-white/[0.06] bg-black/20 px-2 py-1.5 font-mono text-[10px] leading-relaxed text-white/70"
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="text-[#ffb27a]/90">{e.kind}</span>
              <span className="text-white/35">{e.atIso}</span>
              <span className={cn("rounded px-1 text-[9px] uppercase", statusBadgeClass(e.status))}>
                {e.status}
              </span>
            </div>
            <p className="mt-1 whitespace-pre-wrap break-words text-white/50">{meta}</p>
          </li>
        );
      })}
    </ul>
  );
}

function TabEmptyNotWired({ tabId }: { tabId: Exclude<TabId, "activity" | "logs"> }) {
  return (
    <div className="p-3">
      <p className="text-[12px] leading-relaxed text-white/60">{TAB_COPY[tabId]}</p>
    </div>
  );
}

export function WorkspaceChatInspectorPanel({
  onClose,
  sessionId,
  events,
}: WorkspaceChatInspectorPanelProps) {
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
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-white/90">Inspector</h2>
          {sessionId ? (
            <p className="mt-0.5 truncate font-mono text-[10px] text-white/35" title={sessionId}>
              Session {sessionId.slice(0, 12)}…
            </p>
          ) : (
            <p className="mt-0.5 font-mono text-[10px] text-white/35">No session id yet</p>
          )}
        </div>
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
        {activeTab === "activity" ? <ActivityBody events={events} /> : null}
        {activeTab === "logs" ? <LogsBody events={events} /> : null}
        {activeTab === "artifacts" ? <TabEmptyNotWired tabId="artifacts" /> : null}
        {activeTab === "files" ? <TabEmptyNotWired tabId="files" /> : null}
        {activeTab === "memory" ? <TabEmptyNotWired tabId="memory" /> : null}
        {activeTab === "skills" ? <TabEmptyNotWired tabId="skills" /> : null}
      </div>
    </aside>
  );
}

export type { WorkspaceInspectorEvent } from "./workspaceInspectorEvents";
