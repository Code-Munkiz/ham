/**
 * Phase 1c: shown when `/api/me` returns 401 `HAM_WORKSPACE_AUTH_REQUIRED`
 * (local-dev API without `HAM_LOCAL_DEV_WORKSPACE_BYPASS=true`).
 *
 * Rendered only on `/workspace/*` routes by `WorkspaceGate`. Landing and
 * marketing surfaces remain usable.
 */
import * as React from "react";

import { Button } from "@/components/ui/button";

export interface WorkspaceSetupMessageProps {
  onRetry?: () => void;
}

export function WorkspaceSetupMessage({ onRetry }: WorkspaceSetupMessageProps) {
  return (
    <div className="flex h-full w-full items-center justify-center p-6">
      <div className="max-w-xl space-y-4 rounded-2xl border border-white/10 bg-black/40 p-6 text-sm text-foreground">
        <h2 className="text-base font-semibold tracking-tight">
          Workspace API isn&rsquo;t reachable yet
        </h2>
        <p className="text-foreground/80">
          The HAM API responded with{" "}
          <code className="rounded bg-white/5 px-1.5 py-0.5 text-xs">
            HAM_WORKSPACE_AUTH_REQUIRED
          </code>
          . If you&rsquo;re running locally without Clerk, set the dev bypass
          flag and restart the API:
        </p>
        <pre className="overflow-x-auto rounded-md bg-white/5 p-3 text-xs leading-relaxed">
          <code>{`export HAM_LOCAL_DEV_WORKSPACE_BYPASS=true\npython3 scripts/run_local_api.py`}</code>
        </pre>
        <p className="text-foreground/70">
          If you&rsquo;re running against a hosted deployment, sign in with
          Clerk so the dashboard can attach a session JWT.
        </p>
        {onRetry ? (
          <div>
            <Button variant="outline" size="sm" onClick={onRetry} type="button">
              Retry
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
