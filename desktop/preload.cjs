"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const config = ipcRenderer.sendSync("ham-desktop:get-config-sync");

contextBridge.exposeInMainWorld(
  "__HAM_DESKTOP_CONFIG__",
  config && typeof config === "object" ? config : {},
);

/** Narrow Local Control API — no generic IPC invoke. */
const localControlBridge = {
  getStatus: () => ipcRenderer.invoke("ham-desktop:local-control-get-status"),
  getPolicyStatus: () => ipcRenderer.invoke("ham-desktop:local-control-get-policy-status"),
  getAuditStatus: () => ipcRenderer.invoke("ham-desktop:local-control-get-audit-status"),
  getKillSwitchStatus: () => ipcRenderer.invoke("ham-desktop:local-control-get-kill-switch-status"),
  getSidecarStatus: () => ipcRenderer.invoke("ham-desktop:local-control-get-sidecar-status"),
  pingSidecarHealth: () => ipcRenderer.invoke("ham-desktop:local-control-sidecar-health"),
  stopSidecar: () => ipcRenderer.invoke("ham-desktop:local-control-sidecar-stop"),
  startSidecar: () => ipcRenderer.invoke("ham-desktop:local-control-sidecar-start"),
  engageKillSwitch: () => ipcRenderer.invoke("ham-desktop:local-control-engage-kill-switch"),
  armBrowserOnlyControl: () => ipcRenderer.invoke("ham-desktop:local-control-browser-arm"),
  releaseKillSwitchForBrowserMvp: (token) =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-release-kill-switch", token),
  getBrowserStatus: () => ipcRenderer.invoke("ham-desktop:local-control-get-browser-status"),
  startBrowserSession: () => ipcRenderer.invoke("ham-desktop:local-control-browser-start-session"),
  navigateBrowser: (url) => ipcRenderer.invoke("ham-desktop:local-control-browser-navigate", url),
  captureBrowserScreenshot: () =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-screenshot"),
  stopBrowserSession: () => ipcRenderer.invoke("ham-desktop:local-control-browser-stop-session"),
  armRealBrowserControl: () => ipcRenderer.invoke("ham-desktop:local-control-browser-real-arm"),
  getRealBrowserStatus: () =>
    ipcRenderer.invoke("ham-desktop:local-control-get-browser-real-status"),
  startRealBrowserSession: () =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-real-start-session"),
  navigateRealBrowser: (url) =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-real-navigate", url),
  reloadRealBrowser: () => ipcRenderer.invoke("ham-desktop:local-control-browser-real-reload"),
  captureRealBrowserScreenshot: () =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-real-screenshot"),
  realBrowserObserveCompact: () =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-real-observe-compact"),
  realBrowserWaitMs: (ms) => ipcRenderer.invoke("ham-desktop:local-control-browser-real-wait", ms),
  realBrowserScrollVertical: (deltaY) =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-real-scroll", deltaY),
  realBrowserEnumerateClickCandidates: () =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-real-enumerate-candidates"),
  realBrowserClickCandidate: (candidateId) =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-real-click-candidate", candidateId),
  stopRealBrowserSession: () =>
    ipcRenderer.invoke("ham-desktop:local-control-browser-real-stop-session"),
  /** Local web bridge — explicit channel allowlist; no ipcRenderer.invoke escape hatch. */
  webBridge: {
    getStatus: () => ipcRenderer.invoke("ham-desktop:local-control-web-bridge-status"),
    trustedConnect: () =>
      ipcRenderer.invoke("ham-desktop:local-control-web-bridge-trusted-connect"),
    revoke: () => ipcRenderer.invoke("ham-desktop:local-control-web-bridge-pairing-revoke"),
    getPairingConfig: () => ipcRenderer.invoke("ham-desktop:local-control-web-bridge-pairing-get"),
    setPairingConfig: (payload) =>
      ipcRenderer.invoke("ham-desktop:local-control-web-bridge-pairing-set", payload || {}),
    readTrustedStatus: () => ipcRenderer.invoke("ham-desktop:local-control-web-bridge-status-read"),
    browserIntent: (payload) => {
      const p = payload && typeof payload === "object" ? payload : {};
      const action = String(p.action || "").trim();
      const base = {
        intent_id: String(p.intent_id || ""),
        action,
        client_context:
          p.client_context && typeof p.client_context === "object" ? p.client_context : {},
      };
      if (action === "navigate_and_capture") {
        const url = String(p.url || "").trim();
        if (!url)
          return Promise.resolve({
            ok: false,
            error: "invalid_intent",
            reason_code: "invalid_intent",
          });
        return ipcRenderer.invoke("ham-desktop:local-control-web-bridge-browser-intent", {
          ...base,
          url,
        });
      }
      if (action === "observe") {
        return ipcRenderer.invoke("ham-desktop:local-control-web-bridge-browser-intent", base);
      }
      if (action === "click_candidate") {
        const candidateId = String(p.candidate_id || "").trim();
        if (!candidateId)
          return Promise.resolve({
            ok: false,
            error: "invalid_intent",
            reason_code: "invalid_intent",
          });
        return ipcRenderer.invoke("ham-desktop:local-control-web-bridge-browser-intent", {
          ...base,
          candidate_id: candidateId,
        });
      }
      if (action === "scroll") {
        return ipcRenderer.invoke("ham-desktop:local-control-web-bridge-browser-intent", {
          ...base,
          delta_y: Number(p.delta_y || 0),
        });
      }
      if (action === "type_into_field") {
        const selector = String(p.selector || "").trim();
        const text = String(p.text || "");
        if (!selector || !text)
          return Promise.resolve({
            ok: false,
            error: "invalid_intent",
            reason_code: "invalid_intent",
          });
        return ipcRenderer.invoke("ham-desktop:local-control-web-bridge-browser-intent", {
          ...base,
          selector,
          text,
          clear_first: p.clear_first !== false,
        });
      }
      if (action === "key_press") {
        const key = String(p.key || "").trim();
        if (!key)
          return Promise.resolve({
            ok: false,
            error: "invalid_intent",
            reason_code: "invalid_intent",
          });
        return ipcRenderer.invoke("ham-desktop:local-control-web-bridge-browser-intent", {
          ...base,
          key,
        });
      }
      if (action === "wait") {
        return ipcRenderer.invoke("ham-desktop:local-control-web-bridge-browser-intent", {
          ...base,
          wait_ms: Number(p.wait_ms || 0),
        });
      }
      return Promise.resolve({ ok: false, error: "invalid_intent", reason_code: "invalid_intent" });
    },
  },
};

contextBridge.exposeInMainWorld("hamDesktop", {
  localControl: localControlBridge,
});

contextBridge.exposeInMainWorld("__HAM_DESKTOP_BUNDLE__", {
  hermesCliProbe: () => ipcRenderer.invoke("ham-desktop:hermes-cli-probe"),
  runHermesPreset: (preset) => ipcRenderer.invoke("ham-desktop:hermes-preset", preset),
  readCuratedFile: (name) => ipcRenderer.invoke("ham-desktop:read-curated-file", name),
  openHermesUpstreamDocs: () => ipcRenderer.invoke("ham-desktop:open-hermes-upstream-docs"),
  localControl: localControlBridge,
});
