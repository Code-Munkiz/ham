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
      <div className="max-w-xl space-y-4 rounded-2xl border border-amber-300/25 bg-[#07111a] p-6 text-sm text-white shadow-2xl shadow-black/30">
        <h2 className="text-base font-semibold tracking-tight text-amber-50">
          Workspace setup needed
        </h2>
        <p className="text-white/[0.78]">
          HAM could not load a workspace because local workspace bypass is not enabled.
          If you&rsquo;re running locally without Clerk, set the dev bypass flag and
          restart the API.
        </p>
        <pre className="overflow-x-auto rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-xs leading-relaxed text-amber-50">
          <code>{`export HAM_LOCAL_DEV_WORKSPACE_BYPASS=true\npython3 scripts/run_local_api.py`}</code>
        </pre>
        <p className="text-white/60">
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
