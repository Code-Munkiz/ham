import * as React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  connectLocalMachine,
  getBrowserPageOrigin,
  getLocalConnectSetupScript,
  HAM_WORKSPACE_HEALTH_PATH,
  type LocalRuntimeConnectResult,
} from "../adapters/localRuntime";

type ConnectState = LocalRuntimeConnectResult | null;
import { cn } from "@/lib/utils";

type Props = {
  /** @default "card" */
  variant?: "card" | "compact";
  className?: string;
  onSuccess?: () => void;
  showOpenFiles?: boolean;
  showOpenSettings?: boolean;
};

/**
 * One-tap “Connect local machine”: probes default localhost origins for HAM
 * `/api/workspace/health` only, then saves the browser’s local runtime base.
 */
export function LocalMachineConnectCta({
  variant = "card",
  className,
  onSuccess,
  showOpenFiles = true,
  showOpenSettings = true,
}: Props) {
  const [working, setWorking] = React.useState(false);
  const [last, setLast] = React.useState<ConnectState>(null);

  const runConnect = async () => {
    setWorking(true);
    setLast(null);
    try {
      const r = await connectLocalMachine();
      setLast(r);
      if (r.ok) {
        onSuccess?.();
      }
    } finally {
      setWorking(false);
    }
  };

  const copyScript = async () => {
    const text = getLocalConnectSetupScript();
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* ignore */
    }
  };

  const origin = typeof window !== "undefined" ? getBrowserPageOrigin() : "";

  const lastResult = last;

  const successUi =
    lastResult?.ok ? (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2.5 text-[12px] text-emerald-100/95">
        <p className="font-medium">Connected to this machine at {lastResult.base}</p>
        {lastResult.health.workspaceRootPath ? (
          <p className="mt-1.5 text-[11px] text-white/60">
            Filesystem root: <span className="font-mono text-[11px] text-emerald-200/80">{lastResult.health.workspaceRootPath}</span>
          </p>
        ) : null}
        {lastResult.health.broadFilesystemAccess && lastResult.health.workspaceRootPath ? (
          <p className="mt-1 text-[11px] text-amber-200/80">
            Broad filesystem access: {lastResult.health.workspaceRootPath}
          </p>
        ) : null}
        <p className="mt-1.5 break-all font-mono text-[10px] text-white/40">{lastResult.testedUrl}</p>
      </div>
    ) : null;

  let failureUi: React.ReactNode = null;
  if (lastResult && lastResult.ok === false) {
    const err = lastResult;
    failureUi = (
      <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-[12px] text-amber-100/90">
        {err.code === "wrong_service" ? (
          <>
            <p className="font-medium">Wrong service on a local port</p>
            <p className="text-[11px] leading-relaxed text-amber-100/75">
              {err.message} Stop the other app or use a free port. We only treat a response as HAM
              when <span className="font-mono text-[10px]">{HAM_WORKSPACE_HEALTH_PATH}</span> returns the
              expected JSON.
            </p>
          </>
        ) : (
          <>
            <p className="font-medium">Local HAM is not running or the browser blocked it</p>
            <p className="text-[11px] leading-relaxed text-amber-100/70">
              Start the local API, then <strong>Retry</strong>. If the API is already up from current{" "}
              <span className="font-mono text-[10px]">main</span>, a public page calling{" "}
              <span className="font-mono text-[10px]">http://127.0.0.1</span> can still be blocked: allow
              this origin, or restart the server so CORS and private-network preflight include{" "}
              <span className="font-mono text-[10px] break-all text-white/80">
                {origin || "this page’s origin"}
              </span>
              .
            </p>
          </>
        )}
        <details className="text-[11px] text-amber-100/50">
          <summary className="cursor-pointer text-[11px] text-amber-200/70">Start script (copy), then retry</summary>
          <pre className="mt-2 max-h-40 overflow-auto rounded border border-white/10 bg-black/30 p-2 font-mono text-[10px] text-white/70">
            {getLocalConnectSetupScript()}
          </pre>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="secondary" onClick={() => void copyScript()}>
              Copy PowerShell
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => void runConnect()} disabled={working}>
              {working ? "Retrying…" : "Retry connection"}
            </Button>
          </div>
        </details>
      </div>
    );
  }

  return (
    <div
      className={cn(
        variant === "card" && "rounded-xl border border-white/[0.1] bg-white/[0.04] p-4",
        className,
      )}
    >
      {variant === "card" ? (
        <p className="text-[13px] leading-relaxed text-white/60">
          Connect this browser to the HAM API running on <strong className="text-white/80">this computer</strong>. Files and
          Terminal use that process only; cloud APIs cannot read your disk.
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          className="bg-[#e57300] text-white hover:bg-[#c96500] dark:bg-[#d97706] dark:hover:bg-[#b45309]"
          onClick={() => void runConnect()}
          disabled={working}
        >
          {working ? "Connecting…" : "Connect local machine"}
        </Button>
        {showOpenSettings ? (
          <Button type="button" size="sm" variant="outline" asChild>
            <Link to="/workspace/settings?section=connection">Open Connection settings</Link>
          </Button>
        ) : null}
        {showOpenFiles ? (
          <Button type="button" size="sm" variant="ghost" asChild>
            <Link to="/workspace/files">Open Files</Link>
          </Button>
        ) : null}
      </div>
      {last ? <div className="mt-3">{successUi ?? failureUi}</div> : null}
    </div>
  );
}
