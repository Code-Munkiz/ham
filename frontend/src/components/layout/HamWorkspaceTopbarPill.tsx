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

  const baseLabel = (() => {
    switch (ctx.state.status) {
      case "idle":
      case "loading":
        return "Loading…";
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
      case "idle":
        return "bg-foreground/40 animate-pulse";
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
    ctx.state.status === "ready" || ctx.state.status === "onboarding";

  const onPillClick = () => {
    if (ctx.state.status === "error") {
      void ctx.refresh();
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
          "flex items-center gap-2 rounded-full border border-white/10 bg-black/40 px-3 py-1 text-xs text-foreground/90 backdrop-blur transition-colors hover:bg-white/5",
          interactive ? "cursor-pointer" : "",
        )}
        aria-haspopup={interactive ? "menu" : undefined}
        aria-expanded={interactive ? pickerOpen : undefined}
      >
        <span className={cn("inline-block h-1.5 w-1.5 rounded-full", dotClass)} />
        <span className="max-w-[12rem] truncate">{baseLabel}</span>
        {ctx.active?.role ? (
          <span className="rounded bg-white/5 px-1 text-[10px] uppercase tracking-wide text-foreground/70">
            {ctx.active.role}
          </span>
        ) : null}
      </button>
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
