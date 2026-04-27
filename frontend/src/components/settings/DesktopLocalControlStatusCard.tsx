import * as React from "react";
import { Shield, RefreshCw, ExternalLink, AlertCircle, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getHamDesktopLocalControlApi,
  HAM_DESKTOP_BROWSER_MVP_KILL_SWITCH_RELEASE,
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
  const [browserBusy, setBrowserBusy] = React.useState(false);
  const [navUrl, setNavUrl] = React.useState("https://example.com");
  const [screenshotDataUrl, setScreenshotDataUrl] = React.useState<string | null>(null);

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

  const onArmBrowser = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.armBrowserOnlyControl !== "function") return;
    setBrowserBusy(true);
    setErr(null);
    try {
      await api.armBrowserOnlyControl();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Arm browser-only control failed");
    } finally {
      setBrowserBusy(false);
    }
  };

  const onReleaseKillSwitchBrowser = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.releaseKillSwitchForBrowserMvp !== "function") return;
    setBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.releaseKillSwitchForBrowserMvp(HAM_DESKTOP_BROWSER_MVP_KILL_SWITCH_RELEASE);
      if (r && !r.ok) setErr("Release kill switch failed (confirm token rejected).");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Release kill switch failed");
    } finally {
      setBrowserBusy(false);
    }
  };

  const onBrowserStart = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.startBrowserSession !== "function") return;
    setBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.startBrowserSession();
      if (r && "blocked" in r && r.blocked) {
        setErr(`Browser start blocked: ${"reason" in r ? String(r.reason) : ""}`);
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Start browser session failed");
    } finally {
      setBrowserBusy(false);
    }
  };

  const onBrowserNavigate = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.navigateBrowser !== "function") return;
    setBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.navigateBrowser(navUrl.trim());
      if (r && "blocked" in r && r.blocked) {
        setErr(`Navigate blocked: ${"reason" in r ? String(r.reason) : ""}`);
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Navigate failed");
    } finally {
      setBrowserBusy(false);
    }
  };

  const onBrowserScreenshot = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.captureBrowserScreenshot !== "function") return;
    setBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.captureBrowserScreenshot();
      if (r && "ok" in r && r.ok && "data_url" in r) {
        setScreenshotDataUrl(r.data_url);
      } else if (r && "ok" in r && !r.ok) {
        setErr(
          "reason" in r && r.reason
            ? `Screenshot blocked: ${String(r.reason)}`
            : "error" in r && r.error
              ? String(r.error)
              : "Screenshot failed",
        );
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Screenshot failed");
    } finally {
      setBrowserBusy(false);
    }
  };

  const onBrowserStop = async () => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.stopBrowserSession !== "function") return;
    setBrowserBusy(true);
    setErr(null);
    try {
      await api.stopBrowserSession();
      setScreenshotDataUrl(null);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Stop browser failed");
    } finally {
      setBrowserBusy(false);
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
          Local Control (Phase 4A — browser-only MVP)
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
        Phase 4A adds a <span className="text-white/50">Linux-only</span> browser session (Electron{" "}
        <span className="text-white/45">BrowserWindow</span> in main): navigate https only, status, screenshot, stop.
        Default deny; <span className="text-white/50">arm</span> browser-only control, then{" "}
        <span className="text-white/50">release kill switch</span> (audited, explicit token) before starting a session.
        No shell, filesystem, MCP, Droid, Cloud Run, or <span className="text-white/45">/api/browser</span>.
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
        Engage kill switch clears browser arm and blocks sessions. Release kill switch is only for the browser MVP path
        and is audited (not a generic “enable all local control”).
      </p>

      <div className="rounded-lg border border-white/10 bg-black/40 p-4 space-y-3">
        <div className="text-[10px] font-black uppercase tracking-widest text-white/40">Browser-only session (Linux)</div>
        <p className="text-[9px] text-white/35 leading-relaxed">
          Audit log records arm / release / navigate / screenshot / stop — never full URLs with query strings in audit
          lines; screenshots stay in this panel only.
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void onArmBrowser()}
            disabled={loading || browserBusy || !status?.browser_mvp?.supported}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-[#FF6B00]/30 text-[10px] font-black uppercase tracking-widest text-[#FF6B00]/90 hover:border-[#FF6B00]/50 disabled:opacity-40"
          >
            Arm browser-only control
          </button>
          <button
            type="button"
            onClick={() => void onReleaseKillSwitchBrowser()}
            disabled={
              loading ||
              browserBusy ||
              !status?.browser_mvp?.supported ||
              !status?.policy.browser_control_armed
            }
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-500/30 text-[10px] font-black uppercase tracking-widest text-amber-200/80 hover:border-amber-400/50 disabled:opacity-40"
          >
            Release kill switch (browser MVP)
          </button>
          <button
            type="button"
            onClick={() => void onBrowserStart()}
            disabled={
              loading ||
              browserBusy ||
              !status?.browser_mvp?.supported ||
              !!status?.browser_mvp?.gate_blocked_reason
            }
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:border-white/25 disabled:opacity-40"
          >
            Start browser session
          </button>
          <button
            type="button"
            onClick={() => void onBrowserStop()}
            disabled={loading || browserBusy || !status?.browser_mvp?.supported || !status?.browser_mvp.session_running}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:border-amber-500/30 disabled:opacity-40"
          >
            Stop browser session
          </button>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-[9px] text-white/35 min-w-[200px] flex-1">
            Navigate (http/https)
            <input
              value={navUrl}
              onChange={(e) => setNavUrl(e.target.value)}
              disabled={loading || browserBusy || !status?.browser_mvp?.session_running}
              className="rounded-md border border-white/10 bg-black/50 px-2 py-1.5 text-[11px] text-white/80 font-mono"
            />
          </label>
          <button
            type="button"
            onClick={() => void onBrowserNavigate()}
            disabled={
              loading ||
              browserBusy ||
              !status?.browser_mvp?.supported ||
              !status?.browser_mvp.session_running ||
              !!status?.browser_mvp?.gate_blocked_reason
            }
            className="px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/55 hover:border-[#FF6B00]/40 disabled:opacity-40"
          >
            Navigate
          </button>
          <button
            type="button"
            onClick={() => void onBrowserScreenshot()}
            disabled={
              loading ||
              browserBusy ||
              !status?.browser_mvp?.supported ||
              !status?.browser_mvp.session_running ||
              !!status?.browser_mvp?.gate_blocked_reason
            }
            className="px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/55 hover:border-[#FF6B00]/40 disabled:opacity-40"
          >
            Capture screenshot
          </button>
        </div>
        {status?.browser_mvp ? (
          <dl className="grid gap-1.5 text-[10px] text-white/50">
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Supported</dt>
              <dd>{status.browser_mvp.supported ? "yes (Linux)" : "no"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Armed</dt>
              <dd>{status.browser_mvp.armed ? "yes" : "no"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Gate</dt>
              <dd className="font-mono text-[9px] text-white/45">
                {status.browser_mvp.gate_blocked_reason ?? "clear"}
              </dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Session</dt>
              <dd>{status.browser_mvp.session_running ? "running" : "stopped"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Display URL</dt>
              <dd className="font-mono text-[9px] break-all">{status.browser_mvp.display_url || "—"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Title</dt>
              <dd className="break-all">{status.browser_mvp.title || "—"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Loopback URLs</dt>
              <dd>{status.browser_mvp.allow_loopback ? "allowed in policy" : "blocked (default)"}</dd>
            </div>
          </dl>
        ) : null}
        {screenshotDataUrl ? (
          <div className="space-y-1">
            <div className="text-[9px] text-white/35">Last screenshot (local preview)</div>
            <img
              src={screenshotDataUrl}
              alt="Controlled browser screenshot"
              className="max-h-48 rounded border border-white/10 object-contain"
            />
          </div>
        ) : null}
      </div>

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
              {status.kill_switch.engaged ? "engaged" : "disengaged"} ·{" "}
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
            <dd className="text-[10px]">
              browser: {status.capabilities.browser_automation} · other local: not_implemented
            </dd>
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
