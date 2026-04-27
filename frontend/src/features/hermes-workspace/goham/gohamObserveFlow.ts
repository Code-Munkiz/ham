/**
 * GoHAM Mode v0 — managed browser observe/summarize via HAM Desktop local control only.
 * No FastAPI browser plane; no click/type/key.
 */

import {
  HAM_DESKTOP_BROWSER_MVP_KILL_SWITCH_RELEASE,
  type HamDesktopLocalControlApi,
} from "@/lib/ham/desktopBundleBridge";
import { redactUrlForTrail } from "./extractGohamUrl";

export type GoHamTrailStepStatus = "pending" | "active" | "done" | "error";

export type GoHamTrailStep = {
  id: string;
  label: string;
  status: GoHamTrailStepStatus;
  detail?: string;
  /** Slice 3 — optional structured fields for research actions */
  actionType?: string;
  targetRedacted?: string;
  result?: string;
  errorReason?: string;
};

function freshTrail(): GoHamTrailStep[] {
  return [
    { id: "policy", label: "Preparing managed browser policy", status: "pending" },
    { id: "start", label: "Starting managed browser", status: "pending" },
    { id: "nav", label: "Navigating", status: "pending" },
    { id: "observe", label: "Observing page", status: "pending" },
    { id: "summarize", label: "Summarizing", status: "pending" },
    { id: "done", label: "Done", status: "pending" },
  ];
}

function patchTrail(
  steps: GoHamTrailStep[],
  id: string,
  status: GoHamTrailStepStatus,
  detail?: string,
): GoHamTrailStep[] {
  return steps.map((s) => (s.id === id ? { ...s, status, ...(detail !== undefined ? { detail } : {}) } : s));
}

function activate(steps: GoHamTrailStep[], id: string): GoHamTrailStep[] {
  return steps.map((s) => {
    if (s.id === id) return { ...s, status: "active" as const };
    if (s.status === "active") return { ...s, status: "done" as const };
    return s;
  });
}

export function sessionErrorMessage(r: unknown, label: string): string {
  if (!r || typeof r !== "object") return `${label} failed.`;
  const o = r as Record<string, unknown>;
  const detailRaw = o.detail != null ? String(o.detail).trim() : "";
  const detailBlock = detailRaw ? `\n\nTechnical detail: ${detailRaw}` : "";
  if (o.blocked === true) {
    return `${label} blocked: ${o.reason != null ? String(o.reason) : "(no reason)"}`;
  }
  if (o.ok === false && o.reason != null) {
    return `${label}: ${String(o.reason)}`;
  }
  if (o.ok === false && o.error != null) {
    const err = String(o.error);
    if (err === "chromium_not_found") {
      return `${label} failed: Chromium not found — install Chrome/Chromium or run scripts/ensure_chromium_for_desktop.sh, then restart HAM Desktop.${detailBlock}`;
    }
    if (err === "cdp_devtools_timeout") {
      return `${label} failed: Chromium did not open its DevTools port in time. If this persists, set HAM_DESKTOP_CHROME_PATH to a known-good Chrome/Chromium binary and fully restart HAM Desktop.${detailBlock}`;
    }
    if (err === "cdp_no_page_target") {
      return `${label} failed: CDP did not report a page tab yet (no_page_target). Quit stray Chrome instances using the same profile, wait a few seconds, and try again — or fully restart HAM Desktop.${detailBlock}`;
    }
    if (err === "cdp_target_list_failed") {
      return `${label} failed: Could not read DevTools target list from Chromium. Confirm Chrome/Chromium is not blocked by policy and that remote debugging is allowed.${detailBlock}`;
    }
    if (err === "browser_exited_during_attach") {
      return `${label} failed: The managed Chrome window exited or was closed before HAM finished connecting (CDP). Leave the automation window open, close duplicate Chrome profiles using the same HAM session, then try again.${detailBlock}`;
    }
    if (err === "cdp_attach_failed" || err === "cdp_startup_failed") {
      return `${label} failed: could not attach to the browser over CDP (${err}). Update HAM Desktop, quit other apps using ports 9200–9998, and confirm Chrome/Chromium runs locally.${detailBlock}`;
    }
    if (err === "start_failed") {
      return `${label} failed: Desktop hit an unexpected error starting the browser session.${detailBlock}`;
    }
    return `${label} failed: ${err}${detailBlock}`;
  }
  return `${label} failed.`;
}

/** Shared by GoHAM observe + research flows (desktop Local Control gates). */
export async function ensureGohamPolicy(
  api: HamDesktopLocalControlApi,
): Promise<{ ok: true } | { ok: false; reason: string }> {
  let st = await api.getStatus();
  if (!st.browser_real?.supported) {
    return { ok: false, reason: "Managed browser (Phase 4B) is not supported on this platform (Linux required)." };
  }
  if (st.policy.kill_switch.engaged) {
    const rel = await api.releaseKillSwitchForBrowserMvp(HAM_DESKTOP_BROWSER_MVP_KILL_SWITCH_RELEASE);
    if (!rel.ok) {
      return {
        ok: false,
        reason:
          "Kill switch is engaged and could not be released automatically. Open Settings → Local Control in HAM Desktop and release it, then try again.",
      };
    }
  }
  if (!st.policy.real_browser_control_armed) {
    await api.armRealBrowserControl();
  }
  st = await api.getStatus();
  if (st.policy.kill_switch.engaged) {
    return { ok: false, reason: "Kill switch is still engaged after setup. Check Local Control in Settings." };
  }
  if (!st.policy.real_browser_control_armed || !st.policy.permissions?.real_browser_automation) {
    return { ok: false, reason: "Managed browser is not armed. Open HAM Desktop Settings → Local Control to arm real browser control." };
  }
  const gate = st.browser_real?.gate_blocked_reason;
  if (gate) {
    return { ok: false, reason: `Managed browser is blocked: ${gate}` };
  }
  return { ok: true };
}

export type RunGohamObserveOptions = {
  api: HamDesktopLocalControlApi;
  url: string;
  onTrail: (steps: GoHamTrailStep[]) => void;
  shouldAbort: () => boolean;
};

export type RunGohamObserveResult =
  | { ok: true; assistantText: string }
  | { ok: false; userMessage: string; trailSteps: GoHamTrailStep[] };

export async function runGohamObserveFlow(opts: RunGohamObserveOptions): Promise<RunGohamObserveResult> {
  const { api, url, onTrail, shouldAbort } = opts;
  const redacted = redactUrlForTrail(url);
  let steps = freshTrail();

  const update = (next: GoHamTrailStep[]) => {
    steps = next;
    onTrail(steps);
  };

  update(steps);

  if (shouldAbort()) {
    update(patchTrail(activate(steps, "policy"), "policy", "error", "Stopped"));
    return { ok: false, userMessage: "GoHAM was stopped before it started.", trailSteps: steps };
  }

  update(activate(steps, "policy"));
  const pol = await ensureGohamPolicy(api);
  if (pol.ok === false) {
    const reason = pol.reason;
    update(patchTrail(steps, "policy", "error", reason));
    return { ok: false, userMessage: reason, trailSteps: steps };
  }
  update(patchTrail(steps, "policy", "done"));

  if (shouldAbort()) {
    update(patchTrail(steps, "start", "error", "Stopped"));
    return { ok: false, userMessage: "GoHAM stopped.", trailSteps: steps };
  }

  update(activate(steps, "start"));
  const startR = await api.startRealBrowserSession();
  if (!startR || (startR as { ok?: boolean }).ok === false) {
    const msg = sessionErrorMessage(startR, "Start session");
    update(patchTrail(steps, "start", "error", msg));
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: steps };
  }
  update(patchTrail(steps, "start", "done"));

  if (shouldAbort()) {
    await api.stopRealBrowserSession();
    update(patchTrail(steps, "nav", "error", "Stopped"));
    return { ok: false, userMessage: "GoHAM stopped.", trailSteps: steps };
  }

  update(activate(steps, "nav"));
  const navR = await api.navigateRealBrowser(url);
  if (!navR || (navR as { ok?: boolean }).ok === false) {
    const msg = sessionErrorMessage(navR, "Navigate");
    update(patchTrail(steps, "nav", "error", msg));
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: steps };
  }
  update(patchTrail(steps, "nav", "done", redacted));

  if (shouldAbort()) {
    await api.stopRealBrowserSession();
    update(patchTrail(steps, "observe", "error", "Stopped"));
    return { ok: false, userMessage: "GoHAM stopped.", trailSteps: steps };
  }

  update(activate(steps, "observe"));
  const shot = await api.captureRealBrowserScreenshot();
  if (!shot || shot.ok !== true) {
    const msg = sessionErrorMessage(shot, "Screenshot");
    update(patchTrail(steps, "observe", "error", msg));
    await api.stopRealBrowserSession();
    return { ok: false, userMessage: msg, trailSteps: steps };
  }
  const pub = await api.getRealBrowserStatus();
  const title = (pub.title || "").trim() || "(no title)";
  const displayUrl = (pub.display_url || "").trim() || redacted;
  update(patchTrail(steps, "observe", "done", redactUrlForTrail(displayUrl)));

  if (shouldAbort()) {
    await api.stopRealBrowserSession();
    update(patchTrail(steps, "summarize", "error", "Stopped"));
    return { ok: false, userMessage: "GoHAM stopped.", trailSteps: steps };
  }

  update(activate(steps, "summarize"));
  const assistantText = [
    `**GoHAM observation (v0)**`,
    ``,
    `- **Page title:** ${title}`,
    `- **Location:** ${redactUrlForTrail(displayUrl)}`,
    ``,
    `HAM opened this page in the **separate managed browser window** (not your default browser). This v0 readout uses the window title and visible address only — **no full page HTML or stored cookies** are pasted into chat.`,
    ``,
    `Screenshot bytes were captured for local validation only; they are **not embedded** in this message.`,
    ``,
    `The **managed browser window stays open** so you can inspect the page. Click **Stop GoHAM** below when you are done — that closes the session.`,
    ``,
    `---`,
    `**Safety:** GoHAM v0 does not automate forms, logins, purchases, or downloads. Saved passwords from your everyday browser are not used.`,
  ].join("\n");

  update(patchTrail(steps, "summarize", "done"));

  update(activate(steps, "done"));
  update(patchTrail(steps, "done", "done"));

  return { ok: true, assistantText };
}
