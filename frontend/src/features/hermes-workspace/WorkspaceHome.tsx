import * as React from "react";
import { Link } from "react-router-dom";
import { FolderOpen, MessageSquare, Settings, Terminal } from "lucide-react";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import { cn } from "@/lib/utils";
import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

function formatRole(role: HamWorkspaceSummary["role"]): string {
  if (!role) return "";
  return role.charAt(0).toUpperCase() + role.slice(1);
}

function WorkspaceProjectCard({
  workspace,
  isActive,
}: {
  workspace: HamWorkspaceSummary;
  isActive: boolean;
}) {
  return (
    <article
      className={cn(
        "rounded-xl border px-4 py-4 text-left transition-colors",
        isActive
          ? "border-[#c45c12]/40 bg-gradient-to-b from-white/[0.07] to-black/25 shadow-[inset_0_0_0_1px_rgba(255,120,50,0.1)]"
          : "border-[color:var(--ham-workspace-line)] bg-[#040d14]/60 hover:border-white/12",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-tight text-white/92">{workspace.name}</h2>
          <p className="mt-0.5 truncate font-mono text-[11px] text-white/38">{workspace.slug}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          <span className="rounded-md border border-white/[0.08] bg-black/30 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white/50">
            {formatRole(workspace.role)}
          </span>
          <span
            className={cn(
              "rounded-md px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
              workspace.status === "active"
                ? "border border-emerald-500/25 bg-emerald-950/40 text-emerald-100/90"
                : "border border-white/10 bg-white/[0.04] text-white/45",
            )}
          >
            {workspace.status === "active" ? "Active" : "Archived"}
          </span>
        </div>
      </div>
      {workspace.description ? (
        <p className="mt-2 text-[12px] leading-relaxed text-white/45">{workspace.description}</p>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Link
          to="/workspace/chat"
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/85 transition-colors hover:border-white/16 hover:bg-white/[0.07]"
        >
          <MessageSquare className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} aria-hidden />
          Open chat
        </Link>
        <Link
          to="/workspace/files"
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/85 transition-colors hover:border-white/16 hover:bg-white/[0.07]"
        >
          <FolderOpen className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} aria-hidden />
          Open files
        </Link>
        <Link
          to="/workspace/terminal"
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/85 transition-colors hover:border-white/16 hover:bg-white/[0.07]"
        >
          <Terminal className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} aria-hidden />
          Open terminal
        </Link>
        <Link
          to="/workspace/settings"
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[12px] font-medium text-white/85 transition-colors hover:border-white/16 hover:bg-white/[0.07]"
        >
          <Settings className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} aria-hidden />
          Workspace settings
        </Link>
      </div>
    </article>
  );
}

export function WorkspaceHome() {
  const logoSrc = hamWorkspaceLogoUrl();
  const ham = useHamWorkspace();
  const { state, workspaces } = ham;

  const readyList = state.status === "ready" ? workspaces : [];

  return (
    <div className="hww-home flex h-full min-h-0 flex-col overflow-y-auto p-4 sm:p-6 md:p-8">
      <div className="mx-auto w-full max-w-3xl">
        <div className="mb-8 flex flex-col items-center text-center sm:mb-10">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-[#0a1218]/85 shadow-[0_16px_48px_rgba(0,0,0,0.4)]">
            <img src={logoSrc} alt="" className="h-12 w-12 object-contain" width={48} height={48} />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-white/95 sm:text-3xl">Projects</h1>
          <p className="mt-1 text-[12px] font-medium uppercase tracking-[0.14em] text-white/32">
            HAM&apos;s Workspace
          </p>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-white/45">
            Your workspaces and quick links. Open{' '}
            <span className="text-white/55">Library</span> in the sidebar for files, terminal, jobs,
            and more.
          </p>
        </div>

        {state.status === "ready" && readyList.length > 0 ? (
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white/35">
              Your workspaces ({readyList.length})
            </p>
            <ul className="grid gap-3 sm:grid-cols-1">
              {readyList.map((w) => (
                <li key={w.workspace_id}>
                  <WorkspaceProjectCard
                    workspace={w}
                    isActive={
                      state.status === "ready" && state.activeWorkspaceId === w.workspace_id
                    }
                  />
                </li>
              ))}
            </ul>
          </div>
        ) : state.status === "ready" && readyList.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/12 bg-[#040d14]/50 px-6 py-10 text-center">
            <p className="text-sm font-medium text-white/75">No workspaces loaded</p>
            <p className="mt-2 text-[13px] leading-relaxed text-white/40">
              If you just signed in, try refreshing. Otherwise create a workspace from the workspace
              picker when it appears.
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-white/[0.08] bg-[#040d14]/55 px-6 py-10 text-center">
            <p className="text-sm font-medium text-white/80">Sign in to see your projects</p>
            <p className="mt-2 text-[13px] leading-relaxed text-white/42">
              Workspace cards appear here once your account is linked and workspaces are available.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              <Link
                to="/workspace/chat"
                className="inline-flex items-center justify-center rounded-lg border border-[#c45c12]/35 bg-gradient-to-b from-white/[0.08] to-black/25 px-4 py-2 text-sm font-medium text-white/90 shadow-[inset_0_0_0_1px_rgba(255,120,50,0.12)] transition hover:border-[#c45c12]/55"
              >
                Go to chat
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
