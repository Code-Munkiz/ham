/**
 * Phase 1c: branching shell for workspace-scoped routes.
 *
 * Wrap a subtree with `<WorkspaceGate>` when you want it to require an
 * active workspace. The gate:
 *
 * - Renders children unchanged when state is `ready`.
 * - Renders the onboarding screen when state is `onboarding` (zero workspaces).
 * - Renders `WorkspaceSetupMessage` for local-dev `HAM_WORKSPACE_AUTH_REQUIRED`.
 * - Renders children passed through untouched for `auth_required` (lets the
 *   existing Clerk surfaces handle sign-in).
 * - Renders a small inline error block on `error` with a retry button.
 * - Renders a thin loading hint inline while `loading`/`idle`.
 *
 * The gate is intentionally route-agnostic — `App.tsx` decides where it is
 * mounted. Phase 1c does NOT mount this around any existing route to keep
 * the change additive; consumers can opt in later (or it can be wrapped
 * around `WorkspaceApp` in a follow-up PR).
 */
import * as React from "react";

import { Button } from "@/components/ui/button";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";

import { WorkspaceOnboardingScreen } from "./WorkspaceOnboardingScreen";
import { WorkspaceSetupMessage } from "./WorkspaceSetupMessage";

export interface WorkspaceGateProps {
  children: React.ReactNode;
  /** Optional fallback while loading; defaults to a thin status pill. */
  loadingFallback?: React.ReactNode;
}

export function WorkspaceGate({ children, loadingFallback }: WorkspaceGateProps) {
  const ctx = useHamWorkspace();

  switch (ctx.state.status) {
    case "ready":
      return <>{children}</>;

    case "onboarding":
      return (
        <WorkspaceOnboardingScreen
          user={ctx.state.me.user}
          orgs={ctx.state.me.orgs}
          onCreate={ctx.createWorkspace}
        />
      );

    case "setup_needed":
      return <WorkspaceSetupMessage onRetry={() => void ctx.refresh()} />;

    case "auth_required":
      // Clerk handles sign-in elsewhere; pass children through so the existing
      // SignedIn/SignedOut surfaces remain authoritative.
      return <>{children}</>;

    case "error":
      return (
        <div className="flex h-full w-full items-center justify-center p-6">
          <div className="max-w-md space-y-3 rounded-2xl border border-white/10 bg-black/40 p-6 text-sm">
            <p className="font-semibold">Couldn&rsquo;t load workspace</p>
            <p className="text-foreground/70">{ctx.state.message}</p>
            <Button
              size="sm"
              variant="outline"
              type="button"
              onClick={() => void ctx.refresh()}
            >
              Retry
            </Button>
          </div>
        </div>
      );

    case "idle":
    case "loading":
    default:
      return (
        <>
          {loadingFallback ?? (
            <div
              data-testid="workspace-gate-loading"
              className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-black/40 px-3 py-1 text-[11px] text-foreground/70 backdrop-blur"
            >
              Loading workspace…
            </div>
          )}
          {children}
        </>
      );
  }
}
