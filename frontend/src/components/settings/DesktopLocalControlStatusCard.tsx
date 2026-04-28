import * as React from "react";
import { Shield, RefreshCw, ExternalLink, AlertCircle, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getHamDesktopLocalControlApi,
  HAM_DESKTOP_BROWSER_MVP_KILL_SWITCH_RELEASE,
  type HamDesktopLocalControlApi,
  type HamDesktopLocalControlStatus,
} from "@/lib/ham/desktopBundleBridge";

const SPEC_HREF =
  "https://github.com/Code-Munkiz/ham/blob/main/docs/desktop/local_control_v1.md";
const SIDECAR_SPEC_HREF =
  "https://github.com/Code-Munkiz/ham/blob/main/docs/desktop/local_control_sidecar_protocol_v1.md";

const DESKTOP_BRIDGE_HINT =
  "Use the HAM Desktop Electron app from `desktop/` (not a normal browser tab). Fully quit the app and run `npm start` again so preload matches main.";

const STATUS_INVOKE_TIMEOUT_MS = 12_000;

function isDesktopMethod(
  api: ReturnType<typeof getHamDesktopLocalControlApi>,
  name: keyof HamDesktopLocalControlApi,
): boolean {
  return !!(api && typeof (api as Record<string, unknown>)[name as string] === "function");
}

/** Map IPC `{ blocked, reason }` / `{ ok:false, error }` to a user-visible line. */
function opErrorMessage(r: unknown, label: string): string | null {
  if (!r || typeof r !== "object") return null;
  const o = r as Record<string, unknown>;
  if (o.blocked === true) {
    return `${label} blocked: ${o.reason != null ? String(o.reason) : "(no reason)"}`;
  }
  if (o.ok === false && o.reason != null) {
    return `${label}: ${String(o.reason)}`;
  }
  if (o.ok === false && o.error != null) {
    const err = String(o.error);
    if (err === "chromium_not_found") {
      return `${label} failed: ${err} — install Chrome/Chromium/Edge (or Brave), or set HAM_DESKTOP_CHROME_PATH to the binary and restart HAM Desktop.`;
    }
    return `${label} failed: ${err}`;
  }
  return null;
}

function platformLabel(s: HamDesktopLocalControlStatus): string {
  if (s.platform_status === "linux_first") return "Linux first (supported)";
  if (s.platform_status === "windows_planned") return "Windows guarded preview (supported)";
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
  const [realBrowserBusy, setRealBrowserBusy] = React.useState(false);
  const [realNavUrl, setRealNavUrl] = React.useState("https://example.com");
  const [realScreenshotDataUrl, setRealScreenshotDataUrl] = React.useState<string | null>(null);

  const lc = getHamDesktopLocalControlApi();

  /**
   * Refresh status from main. By default does **not** clear `err` — handlers set errors then call
   * `load()`; clearing here was wiping messages (e.g. chromium_not_found) before the user saw them.
   */
  const load = React.useCallback(async (opts?: { clearError?: boolean }) => {
    const api = getHamDesktopLocalControlApi();
    if (typeof api?.getStatus !== "function") return;
    if (opts?.clearError) setErr(null);
    setLoading(true);
    try {
      const s = await Promise.race([
        api.getStatus(),
        new Promise<HamDesktopLocalControlStatus>((_, reject) => {
          window.setTimeout(() => {
            reject(new Error("Local Control status timed out — main process may be busy. Try again or restart HAM Desktop."));
          }, STATUS_INVOKE_TIMEOUT_MS);
        }),
      ]);
      setStatus(s);
    } catch (e) {
      setStatus(null);
      setErr(e instanceof Error ? e.message : "Local Control status failed");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load({ clearError: true });
  }, [load]);

  if (!lc || typeof lc.getStatus !== "function") {
    return null;
  }

  const onEngage = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "engageKillSwitch")) {
      setErr(`Local Control: desktop bridge missing engage. ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setEngageBusy(true);
    setErr(null);
    try {
      await api.engageKillSwitch();
      setRealScreenshotDataUrl(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Engage kill switch failed");
    } finally {
      setEngageBusy(false);
    }
    void load();
  };

  const onStopSidecar = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "stopSidecar")) {
      setErr(`Local Control: desktop bridge missing stopSidecar. ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setSidecarBusy(true);
    setErr(null);
    try {
      await api.stopSidecar();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Stop sidecar failed");
    } finally {
      setSidecarBusy(false);
    }
    void load();
  };

  const onPingSidecarHealth = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "pingSidecarHealth")) {
      setErr(`Local Control: desktop bridge missing pingSidecarHealth. ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setSidecarBusy(true);
    setErr(null);
    try {
      await api.pingSidecarHealth();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Sidecar health ping failed");
    } finally {
      setSidecarBusy(false);
    }
    void load();
  };

  const onArmBrowser = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "armBrowserOnlyControl")) {
      setErr(`Local Control: desktop bridge missing arm (embedded browser). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setBrowserBusy(true);
    setErr(null);
    try {
      await api.armBrowserOnlyControl();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Arm browser-only control failed");
    } finally {
      setBrowserBusy(false);
    }
    void load();
  };

  const onReleaseKillSwitchBrowser = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "releaseKillSwitchForBrowserMvp")) {
      setErr(`Local Control: desktop bridge missing kill-switch release. ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.releaseKillSwitchForBrowserMvp(HAM_DESKTOP_BROWSER_MVP_KILL_SWITCH_RELEASE);
      if (r && !r.ok) setErr("Release kill switch failed (confirm token rejected).");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Release kill switch failed");
    } finally {
      setBrowserBusy(false);
    }
    void load();
  };

  const onBrowserStart = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "startBrowserSession")) {
      setErr(`Local Control: desktop bridge missing start (embedded browser). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.startBrowserSession();
      const msg = opErrorMessage(r, "Embedded browser start");
      if (msg) setErr(msg);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Start browser session failed");
    } finally {
      setBrowserBusy(false);
    }
    void load();
  };

  const onBrowserNavigate = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "navigateBrowser")) {
      setErr(`Local Control: desktop bridge missing navigate. ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.navigateBrowser(navUrl.trim());
      const msg = opErrorMessage(r, "Navigate");
      if (msg) setErr(msg);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Navigate failed");
    } finally {
      setBrowserBusy(false);
    }
    void load();
  };

  const onBrowserScreenshot = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "captureBrowserScreenshot")) {
      setErr(`Local Control: desktop bridge missing screenshot. ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.captureBrowserScreenshot();
      if (r && "ok" in r && r.ok && "data_url" in r) {
        setScreenshotDataUrl(r.data_url);
      } else if (r && "ok" in r && !r.ok) {
        const msg = opErrorMessage(r, "Screenshot");
        setErr(msg ?? "Screenshot failed");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Screenshot failed");
    } finally {
      setBrowserBusy(false);
    }
    void load();
  };

  const onBrowserStop = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "stopBrowserSession")) {
      setErr(`Local Control: desktop bridge missing stop (embedded browser). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setBrowserBusy(true);
    setErr(null);
    try {
      await api.stopBrowserSession();
      setScreenshotDataUrl(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Stop browser failed");
    } finally {
      setBrowserBusy(false);
    }
    void load();
  };

  const onArmRealBrowser = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "armRealBrowserControl")) {
      setErr(`Local Control: desktop bridge missing arm (managed Chromium). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setRealBrowserBusy(true);
    setErr(null);
    try {
      await api.armRealBrowserControl();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Arm real browser control failed");
    } finally {
      setRealBrowserBusy(false);
    }
    void load();
  };

  const onReleaseKillSwitchForReal = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "releaseKillSwitchForBrowserMvp")) {
      setErr(`Local Control: desktop bridge missing kill-switch release. ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setRealBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.releaseKillSwitchForBrowserMvp(HAM_DESKTOP_BROWSER_MVP_KILL_SWITCH_RELEASE);
      if (r && !r.ok) setErr("Release kill switch failed (confirm token rejected).");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Release kill switch failed");
    } finally {
      setRealBrowserBusy(false);
    }
    void load();
  };

  const onRealBrowserStart = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "startRealBrowserSession")) {
      setErr(`Local Control: desktop bridge missing start (managed Chromium). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setRealBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.startRealBrowserSession();
      const msg = opErrorMessage(r, "Managed browser start");
      if (msg) {
        setErr(msg);
      } else if (
        r &&
        typeof r === "object" &&
        "ok" in r &&
        (r as { ok: unknown }).ok === true &&
        isDesktopMethod(api, "navigateRealBrowser")
      ) {
        // Chromium spawns on about:blank by design — load the field URL so the window doesn’t look “stuck”.
        const url = realNavUrl.trim();
        if (url.startsWith("http://") || url.startsWith("https://")) {
          const nav = await api.navigateRealBrowser(url);
          const nmsg = opErrorMessage(nav, "Managed browser navigate");
          if (nmsg) setErr(nmsg);
        }
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Start managed browser failed");
    } finally {
      setRealBrowserBusy(false);
    }
    void load();
  };

  const onRealBrowserNavigate = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "navigateRealBrowser")) {
      setErr(`Local Control: desktop bridge missing navigate (managed Chromium). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setRealBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.navigateRealBrowser(realNavUrl.trim());
      const msg = opErrorMessage(r, "Managed browser navigate");
      if (msg) setErr(msg);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Navigate failed");
    } finally {
      setRealBrowserBusy(false);
    }
    void load();
  };

  const onRealBrowserReload = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "reloadRealBrowser")) {
      setErr(`Local Control: desktop bridge missing reload (managed Chromium). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setRealBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.reloadRealBrowser();
      const msg = opErrorMessage(r, "Managed browser reload");
      if (msg) setErr(msg);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Reload failed");
    } finally {
      setRealBrowserBusy(false);
    }
    void load();
  };

  const onRealBrowserScreenshot = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "captureRealBrowserScreenshot")) {
      setErr(`Local Control: desktop bridge missing screenshot (managed Chromium). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setRealBrowserBusy(true);
    setErr(null);
    try {
      const r = await api.captureRealBrowserScreenshot();
      if (r && "ok" in r && r.ok && "data_url" in r) {
        setRealScreenshotDataUrl(r.data_url);
      } else if (r && "ok" in r && !r.ok) {
        const msg = opErrorMessage(r, "Managed browser screenshot");
        setErr(msg ?? "Screenshot failed");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Screenshot failed");
    } finally {
      setRealBrowserBusy(false);
    }
    void load();
  };

  const onRealBrowserStop = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "stopRealBrowserSession")) {
      setErr(`Local Control: desktop bridge missing stop (managed Chromium). ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setRealBrowserBusy(true);
    setErr(null);
    try {
      await api.stopRealBrowserSession();
      setRealScreenshotDataUrl(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Stop managed browser failed");
    } finally {
      setRealBrowserBusy(false);
    }
    void load();
  };

  const onStartSidecar = async () => {
    const api = getHamDesktopLocalControlApi();
    if (!isDesktopMethod(api, "startSidecar")) {
      setErr(`Local Control: desktop bridge missing startSidecar. ${DESKTOP_BRIDGE_HINT}`);
      return;
    }
    setSidecarBusy(true);
    setErr(null);
    try {
      const r = await api.startSidecar();
      if (r && typeof r === "object" && "ok" in r && r.ok === false && "blocked" in r && r.blocked) {
        setErr("Start blocked: kill switch is engaged (default). Inert sidecar cannot start until policy allows.");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Start sidecar failed");
    } finally {
      setSidecarBusy(false);
    }
    void load();
  };

  return (
    <div className="rounded-xl border border-white/10 bg-[#0c0c0c] p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/35">
          <Shield className="h-4 w-4 text-[#FF6B00]" />
          Local Control (Phase 4A / 4B — desktop browser)
        </div>
        <button
          type="button"
          onClick={() => void load({ clearError: true })}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:text-[#FF6B00] hover:border-[#FF6B00]/30 disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh status
        </button>
      </div>

      <p className="text-[9px] text-white/35 leading-relaxed">
        <span className="text-white/50">Phase 4A</span>: Linux-only{" "}
        <span className="text-white/45">Electron BrowserWindow</span> in main (proof / fallback).{" "}
        <span className="text-white/50">Phase 4B</span>: managed local{" "}
        <span className="text-white/45">Chromium/Chrome</span> with a{" "}
        <span className="text-white/50">HAM-only profile</span>,{" "}
        <span className="text-white/45">127.0.0.1-only CDP</span>, same navigate / status / screenshot / stop gates.
        Default deny; <span className="text-white/50">arm</span> the slice you need, then{" "}
        <span className="text-white/50">release kill switch</span> (audited token) before starting. No attach to your
        default profile, no shell, filesystem, MCP, Droid, Cloud Run, or <span className="text-white/45">/api/browser</span>.
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
        Engage kill switch clears <span className="text-white/40">both</span> browser arms and blocks sessions. Kill-switch
        release uses the same audited browser MVP token for embedded and managed-Chromium paths (not a generic “enable
        all local control”).
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

      <div className="rounded-lg border border-cyan-500/20 bg-black/40 p-4 space-y-3">
        <div className="text-[10px] font-black uppercase tracking-widest text-cyan-200/70">
          Real browser control — managed browser (guarded)
        </div>
        <p className="text-[9px] text-white/35 leading-relaxed">
          HAM spawns a <span className="text-white/50">dedicated Chromium/Chrome profile</span> under desktop userData
          (never your default profile). Debugging listens on <span className="text-white/50">127.0.0.1 only</span> with a
          random port — not exposed beyond localhost. The window may briefly show{" "}
          <span className="text-white/45 font-mono">about:blank</span> or a “Chrome for Testing” banner (Playwright build);
          after <span className="text-white/50">Start</span>, HAM loads the URL in the field below when it is http(s).{" "}
          <span className="text-white/50">Reload</span> refreshes the current page only (no new URL) — explicit,
          panel-only actions; not your default browser and not invokable from Shop.
          Same https-only rules as Phase 4A; loopback blocked unless policy allows.
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void onArmRealBrowser()}
            disabled={loading || realBrowserBusy || !status?.browser_real?.supported}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-cyan-500/35 text-[10px] font-black uppercase tracking-widest text-cyan-200/90 hover:border-cyan-400/55 disabled:opacity-40"
          >
            Arm real browser control
          </button>
          <button
            type="button"
            onClick={() => void onReleaseKillSwitchForReal()}
            disabled={
              loading ||
              realBrowserBusy ||
              !status?.browser_real?.supported ||
              (!status?.policy.browser_control_armed && !status?.policy.real_browser_control_armed)
            }
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-500/30 text-[10px] font-black uppercase tracking-widest text-amber-200/80 hover:border-amber-400/50 disabled:opacity-40"
          >
            Release kill switch (browser MVP)
          </button>
          <button
            type="button"
            onClick={() => void onRealBrowserStart()}
            disabled={
              loading ||
              realBrowserBusy ||
              !status?.browser_real?.supported ||
              !!status?.browser_real?.gate_blocked_reason
            }
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:border-cyan-500/30 disabled:opacity-40"
          >
            Start managed browser
          </button>
          <button
            type="button"
            onClick={() => void onRealBrowserStop()}
            disabled={
              loading || realBrowserBusy || !status?.browser_real?.supported || !status?.browser_real.session_running
            }
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:border-amber-500/30 disabled:opacity-40"
          >
            Stop managed browser
          </button>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-[9px] text-white/35 min-w-[200px] flex-1">
            Navigate (http/https)
            <input
              value={realNavUrl}
              onChange={(e) => setRealNavUrl(e.target.value)}
              disabled={loading || realBrowserBusy || !status?.browser_real?.session_running}
              className="rounded-md border border-white/10 bg-black/50 px-2 py-1.5 text-[11px] text-white/80 font-mono"
            />
          </label>
          <button
            type="button"
            onClick={() => void onRealBrowserNavigate()}
            disabled={
              loading ||
              realBrowserBusy ||
              !status?.browser_real?.supported ||
              !status?.browser_real.session_running ||
              !!status?.browser_real?.gate_blocked_reason
            }
            className="px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/55 hover:border-cyan-500/40 disabled:opacity-40"
          >
            Navigate
          </button>
          <button
            type="button"
            onClick={() => void onRealBrowserReload()}
            disabled={
              loading ||
              realBrowserBusy ||
              !status?.browser_real?.supported ||
              !status?.browser_real.session_running ||
              !!status?.browser_real?.gate_blocked_reason
            }
            className="px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/55 hover:border-cyan-500/40 disabled:opacity-40"
          >
            Reload
          </button>
          <button
            type="button"
            onClick={() => void onRealBrowserScreenshot()}
            disabled={
              loading ||
              realBrowserBusy ||
              !status?.browser_real?.supported ||
              !status?.browser_real.session_running ||
              !!status?.browser_real?.gate_blocked_reason
            }
            className="px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/55 hover:border-cyan-500/40 disabled:opacity-40"
          >
            Capture screenshot
          </button>
        </div>
        {status?.browser_real ? (
          <dl className="grid gap-1.5 text-[10px] text-white/50">
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Supported</dt>
              <dd>{status.browser_real.supported ? "yes (platform supports managed browser)" : "no"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Availability</dt>
              <dd>
                {!status.browser_real.supported
                  ? "unsupported"
                  : status.browser_real.gate_blocked_reason === "chromium_not_found"
                    ? "supported but unavailable (browser executable not found)"
                    : status.browser_real.gate_blocked_reason
                      ? `blocked (${status.browser_real.gate_blocked_reason})`
                      : "available"}
              </dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Managed profile</dt>
              <dd>{status.browser_real.managed_profile ? "yes (HAM-only)" : "no"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">CDP</dt>
              <dd>{status.browser_real.cdp_localhost_only ? "localhost only" : "—"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Uses default OS profile</dt>
              <dd>{status.browser_real.uses_default_profile ? "yes" : "no (never in 4B)"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Armed</dt>
              <dd>{status.browser_real.armed ? "yes" : "no"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Gate</dt>
              <dd className="font-mono text-[9px] text-white/45">
                {status.browser_real.gate_blocked_reason ?? "clear"}
              </dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Session</dt>
              <dd>{status.browser_real.session_running ? "running" : "stopped"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Display URL</dt>
              <dd className="font-mono text-[9px] break-all">{status.browser_real.display_url || "—"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Title</dt>
              <dd className="break-all">{status.browser_real.title || "—"}</dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-white/35">Loopback URLs</dt>
              <dd>{status.browser_real.allow_loopback ? "allowed in policy" : "blocked (default)"}</dd>
            </div>
          </dl>
        ) : null}
        {realScreenshotDataUrl ? (
          <div className="space-y-1">
            <div className="text-[9px] text-white/35">Last real-browser screenshot (local preview)</div>
            <img
              src={realScreenshotDataUrl}
              alt="Managed Chromium screenshot"
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
              browser (4A): {status.capabilities.browser_automation} · real browser CDP (4B):{" "}
              {status.capabilities.real_browser_cdp ?? "—"} · other local: not_implemented
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
