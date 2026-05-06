/**
 * Phase 1c/hosted-safe messaging for `/workspace/*` auth/setup failures.
 * Rendered by `WorkspaceGate` for `setup_needed` / `auth_required`.
 */
import * as React from "react";

import { Button } from "@/components/ui/button";

export interface WorkspaceSetupMessageProps {
  mode?: "setup_needed" | "auth_required" | "auth_not_configured";
  onRetry?: () => void;
  onSignIn?: () => void;
  /** Local-only dev hint; should never be enabled in hosted user-facing builds. */
  showDeveloperHint?: boolean;
}

export function WorkspaceSetupMessage({
  mode = "setup_needed",
  onRetry,
  onSignIn,
  showDeveloperHint = false,
}: WorkspaceSetupMessageProps) {
  const authRequired = mode === "auth_required";
  const authNotConfigured = mode === "auth_not_configured";
  return (
    <div className="flex h-full w-full items-center justify-center p-6">
      <div className="max-w-xl space-y-4 rounded-2xl border border-amber-300/25 bg-[#07111a] p-6 text-sm text-white shadow-2xl shadow-black/30">
        <h2 className="text-base font-semibold tracking-tight text-amber-50">
          {authNotConfigured
            ? "Authentication is not configured"
            : authRequired
              ? "Sign in required"
              : "Workspace unavailable"}
        </h2>
        <p className="text-white/[0.78]">
          {authNotConfigured
            ? "Workspace sign-in is temporarily unavailable. Refresh or contact your workspace admin."
            : authRequired
              ? "Please sign in to load your HAM workspace."
              : "HAM could not load your workspace. Sign in again or contact your workspace admin."}
        </p>

        {showDeveloperHint ? (
          <details className="rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-xs leading-relaxed text-amber-50">
            <summary className="cursor-pointer font-semibold text-amber-100/90">
              Developer details
            </summary>
            <p className="mt-2 text-amber-50/90">
              For local development without Clerk, set a local bypass before starting the API.
            </p>
            <pre className="mt-2 overflow-x-auto rounded border border-amber-300/20 bg-black/25 p-2">
              <code>{`export HAM_LOCAL_DEV_WORKSPACE_BYPASS=true\npython3 scripts/run_local_api.py`}</code>
            </pre>
          </details>
        ) : null}

        {onRetry || onSignIn ? (
          <div className="flex flex-wrap gap-2">
            {onSignIn ? (
              <Button variant="default" size="sm" onClick={onSignIn} type="button">
                Sign in
              </Button>
            ) : null}
            {onRetry ? (
              <Button variant="outline" size="sm" onClick={onRetry} type="button">
                Refresh
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
