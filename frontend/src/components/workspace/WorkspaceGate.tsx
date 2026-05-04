/**
 * Phase 1c: branching shell for workspace-scoped routes.
 *
 * Wrap a subtree with `<WorkspaceGate>` when you want it to require an
 * active workspace. The gate:
 *
 * - Renders children unchanged when state is `ready`.
 * - Renders the onboarding screen when state is `onboarding` (zero workspaces).
 * - Renders `WorkspaceSetupMessage` for `setup_needed` and `auth_required`.
 *   Messaging is hosted-safe by default; optional dev hint is local-only.
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
  const clerkConfigured = Boolean(
    (import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim(),
  );
  const showLocalDevHint =
    import.meta.env.DEV &&
    !clerkConfigured &&
    (import.meta.env.VITE_HAM_SHOW_LOCAL_DEV_HINTS as string | undefined) === "true";
  const goToSignIn = () => {
    window.location.assign("/sign-in");
  };

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
      return (
        <WorkspaceSetupMessage
          mode="setup_needed"
          onRetry={() => void ctx.refresh()}
          showDeveloperHint={showLocalDevHint}
        />
      );

    case "auth_required":
      return (
        <WorkspaceSetupMessage
          mode="auth_required"
          onRetry={() => void ctx.refresh()}
          onSignIn={clerkConfigured ? goToSignIn : undefined}
          showDeveloperHint={showLocalDevHint}
        />
      );

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
