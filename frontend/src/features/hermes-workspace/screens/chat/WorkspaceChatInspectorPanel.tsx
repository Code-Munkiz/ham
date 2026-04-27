/**
 * Upstream `inspector-panel.tsx` structure: header, tab bar, scroll body — honest empty / unavailable
 * per tab. Activity + Logs are wired from real HAM chat stream / session load events only.
 * Memory + Skills: read-only summaries via HAM workspace adapters (lazy-loaded per tab).
 */
import * as React from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { HermesSkillsInstalledResponse } from "@/lib/ham/api";
import {
  workspaceMemoryAdapter,
  type WorkspaceMemoryItem,
} from "../../adapters/memoryAdapter";
import {
  workspaceSkillsAdapter,
  type WorkspaceSkill,
} from "../../adapters/skillsAdapter";
import type { WorkspaceInspectorEvent } from "./workspaceInspectorEvents";
import {
  humanInspectorKindLabel,
  publicMetaSummary,
  statusLabelForUi,
} from "./workspaceInspectorEvents";

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

const TAB_COPY: Record<Exclude<TabId, "activity" | "logs" | "memory" | "skills">, string> = {
  artifacts: "Artifacts are not wired for Workspace chat yet",
  files: "Files are available through the Files workspace, not live Inspector yet",
};

const SKILL_BUILTIN = new Set(["ham-local-docs", "ham-local-plan"]);

function truncate(s: string, max: number): string {
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

function formatMemoryTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

type MemoryInspectorState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; items: WorkspaceMemoryItem[] }
  | { status: "error"; message: string };

type SkillsInspectorState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; skills: WorkspaceSkill[]; catalogCount: number | null; catalogError?: string; live: HermesSkillsInstalledResponse | null }
  | { status: "error"; message: string };

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

function InspectorEventList({
  events,
  emptyText,
  showKindChip,
}: {
  events: WorkspaceInspectorEvent[];
  emptyText: string;
  showKindChip: boolean;
}) {
  if (events.length === 0) {
    return (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/60">{emptyText}</p>
      </div>
    );
  }
  return (
    <ul className="divide-y divide-white/[0.06]">
      {events.map((e) => {
        const extra = publicMetaSummary(e.meta);
        return (
          <li key={e.id} className="px-3 py-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                {showKindChip ? (
                  <p className="mb-1 text-[10px] font-medium text-[#ffb27a]/85">
                    {humanInspectorKindLabel(e.kind)}
                  </p>
                ) : null}
                <p className="text-[12px] leading-snug text-white/[0.88]">{e.summary}</p>
                <p className="mt-1 text-[10px] leading-relaxed text-white/40">
                  {formatClock(e.atIso)}
                  {extra ? <span className="text-white/35"> · {extra}</span> : null}
                </p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium tracking-wide",
                  statusBadgeClass(e.status),
                )}
              >
                {statusLabelForUi(e.status)}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ActivityBody({ events }: { events: WorkspaceInspectorEvent[] }) {
  return (
    <InspectorEventList
      events={events}
      showKindChip={false}
      emptyText="No activity yet. Start a conversation to populate this timeline."
    />
  );
}

function LogsBody({ events }: { events: WorkspaceInspectorEvent[] }) {
  return (
    <InspectorEventList
      events={events}
      showKindChip
      emptyText="No events yet. They will show here after you send a message or load a session."
    />
  );
}

function InspectorLinkRow({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-white/[0.06] px-3 py-2.5">
      <Link
        to={to}
        className="text-[11px] font-medium text-[#ffb27a]/90 underline-offset-2 hover:underline"
      >
        {children}
      </Link>
    </div>
  );
}

function MemoryTabBody({ state, onRetry }: { state: MemoryInspectorState; onRetry: () => void }) {
  if (state.status === "idle" || state.status === "loading") {
    return (
      <div className="space-y-2 p-3">
        <div className="h-3 w-3/4 animate-pulse rounded bg-white/10" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-white/10" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-white/10" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="p-3">
        <p className="text-[12px] font-medium text-white/85">Memory API unavailable.</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-white/55">
          This tab reads from the HAM Workspace Memory API, not the local Files runtime.
        </p>
        <p className="mt-2 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-amber-200/70">
          {state.message}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3 h-7 border-white/20 text-[11px] text-white/80"
          onClick={onRetry}
        >
          Retry
        </Button>
        <InspectorLinkRow to="/workspace/memory">Open Memory</InspectorLinkRow>
      </div>
    );
  }
  if (state.items.length === 0) {
    return (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/70">No memory entries available.</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-white/50">
          Workspace Memory is connected, but no entries are currently stored.
        </p>
        <InspectorLinkRow to="/workspace/memory">Open Memory</InspectorLinkRow>
      </div>
    );
  }
  const shown = state.items.slice(0, 12);
  return (
    <div>
      <ul className="divide-y divide-white/[0.06]">
        {shown.map((m) => (
          <li key={m.id} className="px-3 py-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="min-w-0 truncate text-[12px] font-medium text-white/[0.88]">
                {truncate(m.title || "(untitled)", 56)}
              </span>
              <span className="shrink-0 rounded bg-white/[0.08] px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-white/55">
                {m.kind}
              </span>
              {m.archived ? (
                <span className="shrink-0 rounded bg-white/[0.06] px-1.5 py-0.5 text-[9px] text-white/45">
                  archived
                </span>
              ) : null}
            </div>
            {m.body ? (
              <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-white/45">
                {truncate(m.body.replace(/\s+/g, " "), 120)}
              </p>
            ) : null}
            <p className="mt-1 text-[9px] text-white/35">Updated {formatMemoryTime(m.updatedAt)}</p>
          </li>
        ))}
      </ul>
      {state.items.length > 12 ? (
        <p className="px-3 py-2 text-[10px] text-white/40">+{state.items.length - 12} more in Memory</p>
      ) : null}
      <InspectorLinkRow to="/workspace/memory">Open Memory</InspectorLinkRow>
    </div>
  );
}

function SkillsTabBody({ state, onRetry }: { state: SkillsInspectorState; onRetry: () => void }) {
  if (state.status === "idle" || state.status === "loading") {
    return (
      <div className="space-y-2 p-3">
        <div className="h-3 w-2/3 animate-pulse rounded bg-white/10" />
        <div className="h-3 w-full animate-pulse rounded bg-white/10" />
        <div className="h-3 w-4/5 animate-pulse rounded bg-white/10" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="p-3">
        <p className="text-[12px] font-medium text-white/85">Skills API unavailable.</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-white/55">
          This tab reads from the HAM Workspace Skills API.
        </p>
        <p className="mt-2 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-amber-200/70">
          {state.message}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3 h-7 border-white/20 text-[11px] text-white/80"
          onClick={onRetry}
        >
          Retry
        </Button>
        <InspectorLinkRow to="/workspace/skills">Open Skills</InspectorLinkRow>
      </div>
    );
  }

  const { skills, catalogCount, catalogError, live } = state;
  const hasInstalled = skills.some((s) => s.installed);

  return (
    <div>
      {catalogCount != null ? (
        <p className="border-b border-white/[0.06] px-3 py-2 text-[10px] text-white/50">
          <span className="font-medium text-white/65">{catalogCount}</span> catalog entries available
        </p>
      ) : catalogError ? (
        <p className="border-b border-white/[0.06] px-3 py-2 text-[10px] text-amber-200/70">
          Hermes catalog unavailable.
        </p>
      ) : null}

      {live && live.live_count > 0 ? (
        <p className="border-b border-white/[0.06] px-3 py-1.5 text-[9px] text-white/40">
          Live overlay: {live.live_count} reported · read-only
        </p>
      ) : null}

      {!hasInstalled ? (
        <div className="p-3">
          <p className="text-[12px] leading-relaxed text-white/70">No skills installed yet.</p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-white/50">
            {catalogCount != null && !catalogError
              ? "Hermes static catalog is available read-only."
              : "Install and manage skills from the Skills workspace when available."}
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-white/[0.06]">
          {skills
            .filter((s) => s.installed)
            .slice(0, 16)
            .map((s) => {
              const builtin = SKILL_BUILTIN.has(s.id);
              return (
                <li key={s.id} className="px-3 py-2">
                  <p className="truncate text-[12px] font-medium text-white/[0.88]">{s.name}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {builtin ? (
                      <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[9px] text-sky-200/85">
                        built-in
                      </span>
                    ) : (
                      <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[9px] text-violet-200/85">
                        workspace
                      </span>
                    )}
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 text-[9px]",
                        s.enabled
                          ? "bg-emerald-500/15 text-emerald-200/85"
                          : "bg-white/[0.08] text-white/45",
                      )}
                    >
                      {s.enabled ? "enabled" : "disabled"}
                    </span>
                    <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[9px] text-white/40">
                      read-only
                    </span>
                  </div>
                  {s.description ? (
                    <p className="mt-1 line-clamp-2 text-[10px] text-white/45">
                      {truncate(s.description, 100)}
                    </p>
                  ) : null}
                </li>
              );
            })}
        </ul>
      )}
      {hasInstalled && skills.filter((s) => s.installed).length > 16 ? (
        <p className="px-3 py-2 text-[10px] text-white/40">
          +{skills.filter((s) => s.installed).length - 16} more in Skills
        </p>
      ) : null}
      <InspectorLinkRow to="/workspace/skills">Open Skills</InspectorLinkRow>
    </div>
  );
}

function TabEmptyNotWired({ tabId }: { tabId: "artifacts" | "files" }) {
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
  const [memoryState, setMemoryState] = React.useState<MemoryInspectorState>({ status: "idle" });
  const [skillsState, setSkillsState] = React.useState<SkillsInspectorState>({ status: "idle" });

  const loadMemory = React.useCallback(() => {
    setMemoryState({ status: "loading" });
    void workspaceMemoryAdapter.list(undefined, false).then(({ items, bridge }) => {
      if (bridge.status === "pending") {
        setMemoryState({ status: "error", message: bridge.detail });
      } else {
        setMemoryState({ status: "ready", items });
      }
    });
  }, []);

  const loadSkills = React.useCallback(() => {
    setSkillsState({ status: "loading" });
    void workspaceSkillsAdapter.list().then((inst) => {
      if (inst.bridge.status === "pending") {
        setSkillsState({ status: "error", message: inst.bridge.detail });
        return;
      }
      void Promise.all([
        workspaceSkillsAdapter.hermesStaticCatalog(),
        workspaceSkillsAdapter.hermesLiveOverlay(),
      ]).then(([cat, live]) => {
        const catalogCount =
          cat.data != null ? cat.data.count ?? cat.data.entries.length : null;
        setSkillsState({
          status: "ready",
          skills: inst.skills,
          catalogCount,
          catalogError: cat.bridge.status === "pending" ? cat.bridge.detail : undefined,
          live: live.bridge.status === "ready" ? live.overlay : null,
        });
      });
    });
  }, []);

  React.useEffect(() => {
    if (activeTab !== "memory") return;
    if (memoryState.status !== "idle") return;
    loadMemory();
  }, [activeTab, memoryState.status, loadMemory]);

  React.useEffect(() => {
    if (activeTab !== "skills") return;
    if (skillsState.status !== "idle") return;
    loadSkills();
  }, [activeTab, skillsState.status, loadSkills]);

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
            <p className="mt-0.5 truncate text-[10px] text-white/45">This chat is saved on the server</p>
          ) : (
            <p className="mt-0.5 text-[10px] text-white/45">Start chatting to create a session</p>
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
        {activeTab === "memory" ? (
          <MemoryTabBody state={memoryState} onRetry={loadMemory} />
        ) : null}
        {activeTab === "skills" ? (
          <SkillsTabBody state={skillsState} onRetry={loadSkills} />
        ) : null}
      </div>
    </aside>
  );
}

export type { WorkspaceInspectorEvent } from "./workspaceInspectorEvents";
