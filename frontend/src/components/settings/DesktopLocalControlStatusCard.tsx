import * as React from "react";
import { Shield, RefreshCw, ExternalLink, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getDesktopBundleApi,
  type HamDesktopLocalControlStatus,
} from "@/lib/ham/desktopBundleBridge";

const SPEC_HREF =
  "https://github.com/Code-Munkiz/ham/blob/main/docs/desktop/local_control_v1.md";

function platformLabel(s: HamDesktopLocalControlStatus): string {
  if (s.platform_status === "linux_first") return "Linux first (supported)";
  if (s.platform_status === "windows_planned") return "Windows planned (supported)";
  return "Unsupported for Local Control v1 (macOS / other)";
}

export function DesktopLocalControlStatusCard() {
  const [status, setStatus] = React.useState<HamDesktopLocalControlStatus | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    const b = getDesktopBundleApi();
    const getStatus = b?.localControl?.getStatus;
    if (typeof getStatus !== "function") return;
    setLoading(true);
    setErr(null);
    try {
      const s = await getStatus();
      setStatus(s);
    } catch (e) {
      setStatus(null);
      setErr(e instanceof Error ? e.message : "Local Control status failed");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const b = getDesktopBundleApi();
  if (typeof b?.localControl?.getStatus !== "function") {
    return null;
  }

  return (
    <div className="rounded-xl border border-white/10 bg-[#0c0c0c] p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/35">
          <Shield className="h-4 w-4 text-[#FF6B00]" />
          Local Control (Phase 1 — doctor only)
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:text-[#FF6B00] hover:border-[#FF6B00]/30 disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh status
        </button>
      </div>

      <p className="text-[9px] text-white/35 leading-relaxed">
        Read-only readiness from the Electron main process. Local Control stays <span className="text-white/55">disabled</span>{" "}
        by default — no automation, shell, or filesystem control in this phase.
      </p>

      {err ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-100/90 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          {err}
        </div>
      ) : null}

      {status ? (
        <dl className="grid gap-2 text-[11px] text-white/55">
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Enabled</dt>
            <dd className="font-mono text-white/70">{status.enabled ? "yes" : "no (default)"}</dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Platform</dt>
            <dd>{platformLabel(status)}</dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Phase</dt>
            <dd className="font-mono text-[10px]">{status.phase}</dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Renderer security</dt>
            <dd className="text-[10px]">
              contextIsolation={String(status.security.context_isolation)} · nodeIntegration=
              {String(status.security.node_integration)} · sandbox={String(status.security.sandbox)}
            </dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">User data writable</dt>
            <dd>{status.paths.user_data_writable ? "yes" : "no"}</dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Audit path writable</dt>
            <dd>{status.paths.audit_log_dir_writable ? "yes" : "no"}</dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Automation</dt>
            <dd>None enabled (all capabilities not_implemented)</dd>
          </div>
          {status.warnings.length ? (
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35 shrink-0">Warnings</dt>
              <dd className="font-mono text-[10px] text-amber-200/80">{status.warnings.join(", ")}</dd>
            </div>
          ) : null}
        </dl>
      ) : !err ? (
        <p className="text-xs text-white/30">Loading status…</p>
      ) : null}

      <a
        className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#FF6B00] hover:underline"
        href={SPEC_HREF}
        target="_blank"
        rel="noreferrer"
      >
        Local Control v1 spec (docs) <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}
