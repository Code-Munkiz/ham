/**
 * Phase 1c: minimal workspace pill anchored top-right of the app shell.
 *
 * Always renders something safe: skeleton while loading, dot+label while
 * ready, "Sign in" hint in auth_required, "Setup" in setup_needed, "Retry"
 * in error. The pill **never** prevents the underlying page from mounting.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import type { HamCreateWorkspaceBody } from "@/lib/ham/workspaceApi";

import { WorkspaceOnboardingScreen } from "@/components/workspace/WorkspaceOnboardingScreen";
import { WorkspacePicker } from "@/components/workspace/WorkspacePicker";

export interface HamWorkspaceTopbarPillProps {
  /** Tailwind utility overrides for the wrapper (positioning). */
  className?: string;
}

export function HamWorkspaceTopbarPill({ className }: HamWorkspaceTopbarPillProps) {
  const ctx = useHamWorkspace();
  const [pickerOpen, setPickerOpen] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const clerkConfigured =
    ctx.hostedAuth?.clerkConfigured ??
    Boolean((import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim());
  const showLocalDevHint =
    import.meta.env.DEV &&
    !clerkConfigured &&
    (import.meta.env.VITE_HAM_SHOW_LOCAL_DEV_HINTS as string | undefined) === "true";

  const baseLabel = (() => {
    switch (ctx.state.status) {
      case "idle":
      case "loading":
      case "auth_loading":
        return "Loading…";
      case "auth_not_configured":
        return "Auth not configured";
      case "setup_needed":
        return "Setup needed";
      case "auth_required":
        return "Sign in";
      case "error":
        return "Workspace error";
      case "onboarding":
        return "Pick a workspace";
      case "ready":
        return ctx.active?.name ?? "Pick a workspace";
    }
  })();

  const dotClass = (() => {
    switch (ctx.state.status) {
      case "ready":
        return "bg-emerald-400";
      case "loading":
      case "auth_loading":
      case "idle":
        return "bg-foreground/40 animate-pulse";
      case "auth_not_configured":
      case "auth_required":
      case "setup_needed":
        return "bg-amber-400";
      case "error":
        return "bg-red-400";
      case "onboarding":
        return "bg-sky-400";
    }
  })();

  const interactive =
    ctx.state.status === "ready" ||
    ctx.state.status === "onboarding" ||
    ctx.state.status === "setup_needed" ||
    ctx.state.status === "auth_not_configured" ||
    ctx.state.status === "auth_required" ||
    ctx.state.status === "error";

  const pillClass = (() => {
    switch (ctx.state.status) {
      case "setup_needed":
      case "auth_not_configured":
        return "border-amber-300/45 bg-amber-500/20 text-amber-50 shadow-[0_0_0_1px_rgba(251,191,36,0.12)] hover:bg-amber-500/25";
      case "auth_required":
        return "border-sky-300/45 bg-sky-500/20 text-sky-50 shadow-[0_0_0_1px_rgba(125,211,252,0.12)] hover:bg-sky-500/25";
      case "error":
        return "border-red-300/45 bg-red-500/20 text-red-50 shadow-[0_0_0_1px_rgba(248,113,113,0.12)] hover:bg-red-500/25";
      case "ready":
        return "border-emerald-300/30 bg-emerald-500/[0.12] text-white hover:bg-emerald-500/[0.18]";
      case "onboarding":
        return "border-sky-300/35 bg-sky-500/[0.15] text-white hover:bg-sky-500/20";
      case "idle":
      case "loading":
      case "auth_loading":
        return "border-white/14 bg-white/[0.08] text-white/85";
    }
  })();

  const onPillClick = () => {
    if (ctx.state.status === "error") {
      setDetailsOpen((v) => !v);
      return;
    }
    if (
      ctx.state.status === "setup_needed" ||
      ctx.state.status === "auth_not_configured" ||
      ctx.state.status === "auth_required"
    ) {
      setDetailsOpen((v) => !v);
      return;
    }
    if (ctx.state.status === "onboarding") {
      setCreateOpen(true);
      return;
    }
    if (interactive) setPickerOpen((v) => !v);
  };

  const handleCreate = async (body: HamCreateWorkspaceBody) => {
    const ws = await ctx.createWorkspace(body);
    setCreateOpen(false);
    return ws;
  };

  // Build user/orgs reference for onboarding dialog. Falls back gracefully
  // when state is loading.
  const me =
    ctx.state.status === "ready" || ctx.state.status === "onboarding"
      ? ctx.state.me
      : null;

  return (
    <div className={cn("relative pointer-events-auto", className)}>
      <button
        type="button"
        data-testid="ham-workspace-pill"
        onClick={onPillClick}
        className={cn(
          "flex min-h-8 w-full max-w-full items-center gap-2 rounded-lg border px-3 py-1.5 text-left text-xs font-semibold backdrop-blur transition-colors",
          pillClass,
          interactive ? "cursor-pointer" : "",
        )}
        aria-haspopup={
          ctx.state.status === "ready" || ctx.state.status === "onboarding"
            ? "menu"
            : ctx.state.status === "setup_needed" ||
                ctx.state.status === "auth_not_configured" ||
                ctx.state.status === "auth_required" ||
                ctx.state.status === "error"
              ? "dialog"
              : undefined
        }
        aria-expanded={
          ctx.state.status === "ready" || ctx.state.status === "onboarding"
            ? pickerOpen
            : ctx.state.status === "setup_needed" ||
                ctx.state.status === "auth_not_configured" ||
                ctx.state.status === "auth_required" ||
                ctx.state.status === "error"
              ? detailsOpen
              : undefined
        }
      >
        <span className={cn("inline-block h-1.5 w-1.5 rounded-full", dotClass)} />
        <span className="min-w-0 flex-1 truncate">{baseLabel}</span>
        {ctx.active?.role ? (
          <span className="shrink-0 rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-white/75">
            {ctx.active.role}
          </span>
        ) : null}
      </button>
      {detailsOpen ? (
        <div
          role="dialog"
          aria-label={
            ctx.state.status === "auth_required"
              ? "Sign in required"
              : ctx.state.status === "auth_not_configured"
                ? "Authentication is not configured"
              : "Workspace unavailable"
          }
          className="absolute left-0 top-[calc(100%+0.5rem)] z-50 w-[min(20rem,calc(100vw-2rem))] rounded-xl border border-white/12 bg-[#07111a] p-4 text-left text-xs text-white shadow-2xl shadow-black/45"
        >
          {ctx.state.status === "error" ? (
            <>
              <h2 className="text-sm font-semibold text-red-50">Workspace error</h2>
              <p className="mt-2 leading-relaxed text-white/75">
                HAM could not load workspace context. Retry after checking the local API.
              </p>
              <p className="mt-3 rounded-lg border border-red-300/20 bg-red-300/10 p-3 leading-relaxed text-red-50">
                {ctx.state.message}
              </p>
            </>
          ) : ctx.state.status === "auth_required" ? (
            <>
              <h2 className="text-sm font-semibold text-sky-50">Sign in required</h2>
              <p className="mt-2 leading-relaxed text-white/75">
                Please sign in to load your HAM workspace.
              </p>
            </>
          ) : ctx.state.status === "auth_not_configured" ? (
            <>
              <h2 className="text-sm font-semibold text-amber-50">
                Authentication is not configured
              </h2>
              <p className="mt-2 leading-relaxed text-white/75">
                Set VITE_CLERK_PUBLISHABLE_KEY and redeploy.
              </p>
            </>
          ) : (
            <>
              <h2 className="text-sm font-semibold text-amber-50">Workspace unavailable</h2>
              <p className="mt-2 leading-relaxed text-white/75">
                HAM could not load your workspace. Sign in again or contact your workspace
                admin.
              </p>
            </>
          )}
          {showLocalDevHint ? (
            <details className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/10 p-3 text-[11px] text-amber-50">
              <summary className="cursor-pointer font-semibold text-amber-100/85">
                Developer setup (local-only)
              </summary>
              <pre className="mt-2 overflow-x-auto rounded border border-amber-300/20 bg-black/35 p-2">
                <code>{`export HAM_LOCAL_DEV_WORKSPACE_BYPASS=true\npython3 scripts/run_local_api.py`}</code>
              </pre>
            </details>
          ) : null}
          <div className="mt-4 flex items-center gap-2">
            {ctx.state.status === "auth_required" && clerkConfigured ? (
              <button
                type="button"
                onClick={() => ctx.openSignIn?.()}
                className="rounded-lg border border-sky-300/25 bg-sky-400/20 px-3 py-1.5 text-xs font-semibold text-sky-50 transition hover:bg-sky-400/30"
              >
                Sign in
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void ctx.refresh()}
              className="rounded-lg border border-white/14 bg-white/10 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/[0.15]"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={() => setDetailsOpen(false)}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-white/65 transition hover:bg-white/[0.08] hover:text-white"
            >
              Close
            </button>
          </div>
        </div>
      ) : null}
      {ctx.state.status === "ready" || ctx.state.status === "onboarding" ? (
        <WorkspacePicker
          workspaces={ctx.workspaces}
          activeWorkspaceId={
            ctx.state.status === "ready" ? ctx.state.activeWorkspaceId : null
          }
          open={pickerOpen}
          onSelect={ctx.selectWorkspace}
          onCreate={() => setCreateOpen(true)}
          onClose={() => setPickerOpen(false)}
        />
      ) : null}
      {createOpen && me ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          data-testid="ham-workspace-create-dialog"
          onClick={(ev) => {
            if (ev.target === ev.currentTarget) setCreateOpen(false);
          }}
        >
          <WorkspaceOnboardingScreen
            user={me.user}
            orgs={me.orgs}
            onCreate={handleCreate}
            onDismiss={() => setCreateOpen(false)}
            allowDismiss
            variant="dialog"
          />
        </div>
      ) : null}
    </div>
  );
}
