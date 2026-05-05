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
import { WORKSPACE_API_UNREACHABLE_USER_COPY } from "./workspaceApiUnreachableCopy";

export interface WorkspaceGateProps {
  children: React.ReactNode;
  /** Optional fallback while loading; defaults to a thin status pill. */
  loadingFallback?: React.ReactNode;
}

export function WorkspaceGate({ children, loadingFallback }: WorkspaceGateProps) {
  const ctx = useHamWorkspace();
  const clerkConfigured =
    ctx.hostedAuth?.clerkConfigured ??
    Boolean((import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim());
  const showLocalDevHint =
    import.meta.env.DEV &&
    !clerkConfigured &&
    (import.meta.env.VITE_HAM_SHOW_LOCAL_DEV_HINTS as string | undefined) === "true";
  const openSignIn = ctx.openSignIn;

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
          onSignIn={clerkConfigured ? openSignIn : undefined}
          showDeveloperHint={showLocalDevHint}
        />
      );

    case "auth_not_configured":
      return (
        <WorkspaceSetupMessage
          mode="auth_not_configured"
          onRetry={() => void ctx.refresh()}
          showDeveloperHint={showLocalDevHint}
        />
      );

    case "error": {
      const net = ctx.state.networkUnreachable;
      return (
        <div className="flex h-full w-full items-center justify-center p-6">
          <div className="max-w-md space-y-3 rounded-2xl border border-white/10 bg-black/40 p-6 text-sm">
            <p className="font-semibold">Workspace unavailable</p>
            {net ? (
              <>
                <p className="text-foreground/85">{WORKSPACE_API_UNREACHABLE_USER_COPY}</p>
              </>
            ) : (
              <p className="text-foreground/70">
                We couldn&apos;t load your workspace. Refresh or contact your workspace admin.
              </p>
            )}
            {showLocalDevHint ? (
              <details className="rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-xs leading-relaxed text-amber-50">
                <summary className="cursor-pointer font-semibold text-amber-100/90">
                  Developer details
                </summary>
                {net ? (
                  <p className="mt-2 break-all">
                    API endpoint: <span className="font-mono">{net.apiOrigin}</span>
                  </p>
                ) : null}
                <p className="mt-2 break-words">{ctx.state.message}</p>
                {ctx.state.code ? <p className="mt-1">Code: <span className="font-mono">{ctx.state.code}</span></p> : null}
              </details>
            ) : null}
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" variant="outline" type="button" onClick={() => void ctx.refresh()}>
                Refresh
              </Button>
              {showLocalDevHint && net ? (
                <Button size="sm" variant="outline" asChild>
                  <a href={net.statusUrl} target="_blank" rel="noopener noreferrer">
                    Open API status
                  </a>
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      );
    }

    case "auth_loading":
    case "idle":
    case "loading":
    default:
      return (
        <div className="flex h-full w-full items-center justify-center p-6">
          {loadingFallback ?? (
            <div
              data-testid="workspace-gate-loading"
              className="rounded-full bg-black/40 px-3 py-1 text-[11px] text-foreground/70 backdrop-blur"
            >
              {ctx.state.status === "auth_loading" ? "Initializing sign-in…" : "Loading workspace…"}
            </div>
          )}
        </div>
      );
  }
}
