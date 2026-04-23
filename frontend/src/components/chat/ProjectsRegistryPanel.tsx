import * as React from "react";
import { Activity, Folder, ExternalLink, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ProjectRecord } from "@/lib/ham/types";
import {
  getProjectDefaultDeployPolicy,
  PROJECT_DEFAULT_DEPLOY_POLICY_OPTIONS,
  type ProjectDefaultDeployPolicy,
} from "@/lib/ham/projectDeployPolicy";

export type RecentMissionShortcut = { id: string; label?: string; t: number };

export type ProjectsRegistryPanelProps = {
  mountRepo: string;
  setMountRepo: (v: string) => void;
  mountRef: string;
  setMountRef: (v: string) => void;
  activeCloudAgentId: string | null;
  setActiveCloudAgentIdLive: (v: string | null) => void;
  onActiveMissionBlurCommit: (trimmed: string) => void;
  recentMissions: RecentMissionShortcut[];
  formatShortcutAge: (t: number) => string;
  onShortcutUse: (id: string) => void;
  projects: ProjectRecord[];
  projectsLoading: boolean;
  /** Deeper operational log stream (not a second mission board). */
  onOpenActivity: () => void;
  /** Bind chat context to this registered project. */
  onBindProject: (projectId: string) => void;
  onUpdateProjectDefaultPolicy: (projectId: string, policy: ProjectDefaultDeployPolicy) => Promise<void>;
  activeCloudAgentIdForShortcut: string | null;
  onClose: () => void;
};

function truncPath(s: string, max = 42): string {
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

export function ProjectsRegistryPanel({
  mountRepo,
  setMountRepo,
  mountRef,
  setMountRef,
  activeCloudAgentId,
  setActiveCloudAgentIdLive,
  onActiveMissionBlurCommit,
  recentMissions,
  formatShortcutAge,
  onShortcutUse,
  projects,
  projectsLoading,
  onOpenActivity,
  onBindProject,
  onUpdateProjectDefaultPolicy,
  activeCloudAgentIdForShortcut,
  onClose,
}: ProjectsRegistryPanelProps) {
  const [policyBusy, setPolicyBusy] = React.useState<string | null>(null);

  const setPolicy = async (projectId: string, policy: ProjectDefaultDeployPolicy) => {
    setPolicyBusy(projectId);
    try {
      await onUpdateProjectDefaultPolicy(projectId, policy);
    } finally {
      setPolicyBusy(null);
    }
  };

  return (
    <div className="flex h-full w-full max-w-md flex-col border-l border-white/10 bg-[#0a0a0a]/95 text-white shadow-2xl backdrop-blur-xl">
      <div className="shrink-0 space-y-2 border-b border-white/10 px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-0.5 pr-1">
            <h2 className="text-[10px] font-black uppercase tracking-[0.2em] text-[#BC13FE]">Projects</h2>
            <p className="text-[9px] leading-relaxed text-white/35">
              Mount, mission bind, and defaults. Mission progress lives in{" "}
              <span className="text-white/50">Overview</span> and{" "}
              <span className="text-white/50">History</span> — not here.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={onOpenActivity}
              className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-white/[0.04] px-2 py-1.5 text-[8px] font-black uppercase tracking-widest text-white/55 transition-colors hover:border-[#FF6B00]/40 hover:text-[#FF6B00]"
            >
              <Activity className="h-3 w-3" />
              Activity
              <ExternalLink className="h-2.5 w-2.5 opacity-40" aria-hidden />
            </button>
            <button type="button" onClick={onClose} className="p-1.5 text-white/40 hover:text-white" aria-label="Close">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-0 overflow-y-auto [scrollbar-gutter:stable]">
        <section className="border-b border-white/[0.06] px-4 py-3">
          <p className="text-[8px] font-black uppercase tracking-widest text-white/30">Workspace mount</p>
          <div className="mt-2 rounded-md border border-white/8 bg-white/[0.02] p-2.5">
            <label className="text-[8px] font-bold uppercase tracking-wider text-white/30">Repository</label>
            <input
              value={mountRepo}
              onChange={(e) => setMountRepo(e.target.value)}
              placeholder="https://github.com/org/repo"
              className="mb-2 mt-1 w-full border border-white/10 bg-black/50 px-2 py-1.5 text-[11px] text-white/90 outline-none focus:border-[#FF6B00]/40"
            />
            <label className="text-[8px] font-bold uppercase tracking-wider text-white/30">Ref</label>
            <input
              value={mountRef}
              onChange={(e) => setMountRef(e.target.value)}
              placeholder="main"
              className="mt-1 w-full border border-white/10 bg-black/50 px-2 py-1.5 text-[11px] text-white/90 outline-none focus:border-[#FF6B00]/40"
            />
          </div>
        </section>

        <section className="border-b border-white/[0.06] px-4 py-3">
          <p className="text-[8px] font-black uppercase tracking-widest text-white/30">Active mission id</p>
          <p className="mt-0.5 text-[9px] text-white/22">Binds the Cloud execution pane (right). Use Launch or clear to disconnect.</p>
          <input
            value={activeCloudAgentId ?? ""}
            onChange={(e) => setActiveCloudAgentIdLive(e.target.value.trim() || null)}
            onBlur={(e) => onActiveMissionBlurCommit(e.target.value.trim())}
            placeholder="Cursor agent id…"
            className="mt-2 w-full rounded border border-white/8 bg-black/50 px-2 py-1.5 font-mono text-[11px] text-white/90 outline-none focus:border-[#FF6B00]/40"
          />
        </section>

        <section className="border-b border-white/[0.06] px-4 py-3">
          <div className="flex items-center gap-2 text-[#BC13FE]/90">
            <Folder className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <p className="text-[8px] font-black uppercase tracking-widest">Registered projects</p>
          </div>
          {projectsLoading ? (
            <p className="mt-2 text-[10px] text-white/30">Loading…</p>
          ) : projects.length === 0 ? (
            <p className="mt-2 text-[10px] text-white/25">None on this API.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {projects.map((p) => {
                const policy = getProjectDefaultDeployPolicy(p);
                const busy = policyBusy === p.id;
                return (
                  <li
                    key={p.id}
                    className="rounded-md border border-white/8 bg-black/30 p-2.5"
                    title={p.root}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[12px] font-bold text-white/90">{p.name}</p>
                        <p className="mt-0.5 font-mono text-[8px] text-white/28">{p.id}</p>
                        <p className="mt-0.5 text-[8px] text-white/20">{truncPath(p.root)}</p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <button
                          type="button"
                          onClick={() => onBindProject(p.id)}
                          className="text-[8px] font-black uppercase tracking-widest text-[#FF6B00] hover:text-white"
                        >
                          Open
                        </button>
                        <button
                          type="button"
                          onClick={onOpenActivity}
                          className="text-[8px] font-black uppercase tracking-widest text-white/40 hover:text-[#00E5FF]/90"
                        >
                          View activity
                        </button>
                      </div>
                    </div>
                    <div className="mt-2 border-t border-white/[0.06] pt-2">
                      <label
                        className="text-[7px] font-bold uppercase tracking-widest text-white/32"
                        htmlFor={`def-pol-${p.id}`}
                      >
                        Default deploy policy
                      </label>
                      <p className="mb-1.5 text-[7px] leading-relaxed text-white/18">
                        For new work on this project; live mission gating stays in{" "}
                        <span className="text-white/30">Overview</span>. Server env can still set the baseline.
                      </p>
                      <select
                        id={`def-pol-${p.id}`}
                        className={cn(
                          "w-full cursor-pointer rounded border border-white/10 bg-black/50 px-2 py-1.5 text-[11px] text-white/85 outline-none focus:border-[#BC13FE]/50",
                          busy && "opacity-60",
                        )}
                        value={policy}
                        disabled={busy}
                        onChange={(e) =>
                          void setPolicy(p.id, e.target.value as ProjectDefaultDeployPolicy)
                        }
                      >
                        {PROJECT_DEFAULT_DEPLOY_POLICY_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="px-4 py-3 pb-8">
          <p className="text-[8px] font-black uppercase tracking-widest text-white/30">Local shortcuts</p>
          <p className="mt-0.5 text-[9px] text-white/20">This browser only. Server missions: History.</p>
          {recentMissions.length === 0 ? (
            <p className="mt-2 text-[10px] text-white/25">Empty.</p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {[...recentMissions]
                .sort((a, b) => b.t - a.t)
                .map((m) => {
                  const isActive = (activeCloudAgentIdForShortcut ?? "").trim() === m.id.trim();
                  return (
                    <li
                      key={m.id}
                      className="flex items-stretch justify-between gap-2 rounded border border-white/8 bg-white/[0.02]"
                    >
                      <div className="min-w-0 flex-1 px-2 py-1.5">
                        <p className="font-mono text-[10px] text-[#00E5FF]/90">
                          {m.id.length > 22 ? `${m.id.slice(0, 7)}…${m.id.slice(-5)}` : m.id}
                        </p>
                        {m.label ? <p className="truncate text-[8px] text-white/35">{m.label}</p> : null}
                        <p className="text-[7px] text-white/15">{formatShortcutAge(m.t)}</p>
                      </div>
                      <div className="flex min-w-0 flex-col border-l border-white/8">
                        {isActive ? (
                          <span className="self-center px-1 pt-0.5 text-[7px] font-black uppercase text-emerald-400/80">
                            Active
                          </span>
                        ) : null}
                        <button
                          type="button"
                          className="flex-1 px-2.5 text-[8px] font-black uppercase tracking-widest text-[#FF6B00] hover:bg-white/5"
                          onClick={() => onShortcutUse(m.id)}
                        >
                          Use
                        </button>
                      </div>
                    </li>
                  );
                })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
