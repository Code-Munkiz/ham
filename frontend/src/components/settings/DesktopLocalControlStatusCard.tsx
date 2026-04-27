import * as React from "react";
import { Shield, RefreshCw, ExternalLink, AlertCircle, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getHamDesktopLocalControlApi,
  type HamDesktopLocalControlStatus,
} from "@/lib/ham/desktopBundleBridge";

const SPEC_HREF =
  "https://github.com/Code-Munkiz/ham/blob/main/docs/desktop/local_control_v1.md";
const SIDECAR_SPEC_HREF =
  "https://github.com/Code-Munkiz/ham/blob/main/docs/desktop/local_control_sidecar_protocol_v1.md";

function platformLabel(s: HamDesktopLocalControlStatus): string {
  if (s.platform_status === "linux_first") return "Linux first (supported)";
  if (s.platform_status === "windows_planned") return "Windows planned (supported)";
  return "Unsupported for Local Control v1 (macOS / other)";
}

export function DesktopLocalControlStatusCard() {
  const [status, setStatus] = React.useState<HamDesktopLocalControlStatus | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [engageBusy, setEngageBusy] = React.useState(false);
  const [sidecarBusy, setSidecarBusy] = React.useState(false);

  const lc = getHamDesktopLocalControlApi();

  const load = React.useCallback(async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.getStatus !== "function") return;
    setLoading(true);
    setErr(null);
    try {
      const s = await api.getStatus();
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

  if (!lc || typeof lc.getStatus !== "function") {
    return null;
  }

  const onEngage = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.engageKillSwitch !== "function") return;
    setEngageBusy(true);
    setErr(null);
    try {
      await api.engageKillSwitch();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Engage kill switch failed");
    } finally {
      setEngageBusy(false);
    }
  };

  const onStopSidecar = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.stopSidecar !== "function") return;
    setSidecarBusy(true);
    setErr(null);
    try {
      await api.stopSidecar();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Stop sidecar failed");
    } finally {
      setSidecarBusy(false);
    }
  };

  const onPingSidecarHealth = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.pingSidecarHealth !== "function") return;
    setSidecarBusy(true);
    setErr(null);
    try {
      await api.pingSidecarHealth();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Sidecar health ping failed");
    } finally {
      setSidecarBusy(false);
    }
  };

  const onStartSidecar = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.startSidecar !== "function") return;
    setSidecarBusy(true);
    setErr(null);
    try {
      const r = await api.startSidecar();
      if (r && typeof r === "object" && "ok" in r && r.ok === false && "blocked" in r && r.blocked) {
        setErr("Start blocked: kill switch is engaged (default). Inert sidecar cannot start until policy allows.");
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Start sidecar failed");
    } finally {
      setSidecarBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-white/10 bg-[#0c0c0c] p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/35">
          <Shield className="h-4 w-4 text-[#FF6B00]" />
          Local Control (Phase 3B — inert sidecar shell)
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
        Local Control stays <span className="text-white/55">disabled</span> by default. Kill switch defaults{" "}
        <span className="text-white/55">engaged</span>, which <span className="text-white/50">blocks starting</span> the
        inert sidecar. Phase 3B ships an <span className="text-white/50">stdio-only child</span> (health / status /
        shutdown) — no tools, no automation, no inbound network, no Droid access.
      </p>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void onEngage()}
          disabled={engageBusy || loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-emerald-500/25 text-[10px] font-black uppercase tracking-widest text-emerald-200/90 hover:border-emerald-400/50 disabled:opacity-50"
        >
          <Lock className={cn("h-3.5 w-3.5", engageBusy && "animate-pulse")} />
          Engage kill switch
        </button>
        <button
          type="button"
          onClick={() => void onPingSidecarHealth()}
          disabled={loading || sidecarBusy || !status?.sidecar.running}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:text-[#FF6B00] hover:border-[#FF6B00]/30 disabled:opacity-50"
        >
          Ping sidecar health
        </button>
        <button
          type="button"
          onClick={() => void onStopSidecar()}
          disabled={loading || sidecarBusy || !status?.sidecar.running}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:text-amber-200/90 hover:border-amber-500/30 disabled:opacity-50"
        >
          Stop sidecar
        </button>
        <button
          type="button"
          onClick={() => void onStartSidecar()}
          disabled={loading || sidecarBusy || !status?.sidecar.start_allowed || !!status?.sidecar.running}
          title={
            status && !status.sidecar.start_allowed
              ? "Start is blocked while the kill switch is engaged (default)."
              : undefined
          }
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/40 hover:border-white/20 disabled:opacity-40"
        >
          Start sidecar
        </button>
      </div>
      <p className="text-[8px] text-white/25 leading-relaxed">
        Engage is idempotent and only makes policy safer (never disables the kill switch from this UI).
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
            <dt className="text-white/35 shrink-0">Kill switch</dt>
            <dd>
              {status.kill_switch.engaged ? "engaged" : "engaged (unexpected — refresh)"} ·{" "}
              <span className="font-mono text-[10px] text-white/45">{status.kill_switch.reason}</span>
            </dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Policy</dt>
            <dd>
              Default deny · persisted: {status.policy.persisted ? "yes" : "no (in-memory default)"}
            </dd>
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
            <dt className="text-white/35 shrink-0">Audit log</dt>
            <dd>
              available: {status.audit.available ? "yes" : "no"} · writable: {status.audit.writable ? "yes" : "no"}
              {status.audit.event_count_estimate != null
                ? ` · events (est.): ${status.audit.event_count_estimate}`
                : ""}{" "}
              · redacted
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
            <dt className="text-white/35 shrink-0">Sidecar</dt>
            <dd className="text-[10px] leading-relaxed">
              implemented: {status.sidecar.implemented ? "yes (inert shell)" : "no"} · {status.sidecar.mode} · running:{" "}
              {status.sidecar.running ? "yes" : "no"} · transport:{" "}
              <span className="font-mono text-white/45">{status.sidecar.transport}</span> · health:{" "}
              <span className="font-mono text-white/45">{status.sidecar.health}</span> · start allowed:{" "}
              {status.sidecar.start_allowed ? "yes" : "no"}
              {status.sidecar.blocked_reason ? (
                <>
                  {" "}
                  · blocked: <span className="font-mono text-white/45">{status.sidecar.blocked_reason}</span>
                </>
              ) : null}{" "}
              · inbound network: {status.sidecar.inbound_network ? "yes" : "no"} · Droid: {status.sidecar.droid_access}
            </dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Sidecar capabilities</dt>
            <dd className="text-[10px]">all not_implemented</dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="text-white/35 shrink-0">Capabilities</dt>
            <dd>not implemented (no automation)</dd>
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

      <div className="flex flex-wrap gap-4">
        <a
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#FF6B00] hover:underline"
          href={SPEC_HREF}
          target="_blank"
          rel="noreferrer"
        >
          Local Control v1 spec (docs) <ExternalLink className="h-3 w-3" />
        </a>
        <a
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#FF6B00]/80 hover:underline"
          href={SIDECAR_SPEC_HREF}
          target="_blank"
          rel="noreferrer"
        >
          Sidecar protocol v1 (design) <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
}
