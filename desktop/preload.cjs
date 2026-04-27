'use strict';

const { contextBridge, ipcRenderer } = require('electron');

const config = ipcRenderer.sendSync('ham-desktop:get-config-sync');

contextBridge.exposeInMainWorld('__HAM_DESKTOP_CONFIG__', config && typeof config === 'object' ? config : {});

/** Narrow Local Control API — no generic IPC invoke. */
const localControlBridge = {
  getStatus: () => ipcRenderer.invoke('ham-desktop:local-control-get-status'),
  getPolicyStatus: () => ipcRenderer.invoke('ham-desktop:local-control-get-policy-status'),
  getAuditStatus: () => ipcRenderer.invoke('ham-desktop:local-control-get-audit-status'),
  getKillSwitchStatus: () => ipcRenderer.invoke('ham-desktop:local-control-get-kill-switch-status'),
  getSidecarStatus: () => ipcRenderer.invoke('ham-desktop:local-control-get-sidecar-status'),
  pingSidecarHealth: () => ipcRenderer.invoke('ham-desktop:local-control-sidecar-health'),
  stopSidecar: () => ipcRenderer.invoke('ham-desktop:local-control-sidecar-stop'),
  startSidecar: () => ipcRenderer.invoke('ham-desktop:local-control-sidecar-start'),
  engageKillSwitch: () => ipcRenderer.invoke('ham-desktop:local-control-engage-kill-switch'),
  armBrowserOnlyControl: () => ipcRenderer.invoke('ham-desktop:local-control-browser-arm'),
  releaseKillSwitchForBrowserMvp: (token) =>
    ipcRenderer.invoke('ham-desktop:local-control-browser-release-kill-switch', token),
  getBrowserStatus: () => ipcRenderer.invoke('ham-desktop:local-control-get-browser-status'),
  startBrowserSession: () => ipcRenderer.invoke('ham-desktop:local-control-browser-start-session'),
  navigateBrowser: (url) => ipcRenderer.invoke('ham-desktop:local-control-browser-navigate', url),
  captureBrowserScreenshot: () => ipcRenderer.invoke('ham-desktop:local-control-browser-screenshot'),
  stopBrowserSession: () => ipcRenderer.invoke('ham-desktop:local-control-browser-stop-session'),
  armRealBrowserControl: () => ipcRenderer.invoke('ham-desktop:local-control-browser-real-arm'),
  getRealBrowserStatus: () => ipcRenderer.invoke('ham-desktop:local-control-get-browser-real-status'),
  startRealBrowserSession: () => ipcRenderer.invoke('ham-desktop:local-control-browser-real-start-session'),
  navigateRealBrowser: (url) => ipcRenderer.invoke('ham-desktop:local-control-browser-real-navigate', url),
  reloadRealBrowser: () => ipcRenderer.invoke('ham-desktop:local-control-browser-real-reload'),
  captureRealBrowserScreenshot: () => ipcRenderer.invoke('ham-desktop:local-control-browser-real-screenshot'),
  stopRealBrowserSession: () => ipcRenderer.invoke('ham-desktop:local-control-browser-real-stop-session'),
};

contextBridge.exposeInMainWorld('hamDesktop', {
  localControl: localControlBridge,
});

contextBridge.exposeInMainWorld('__HAM_DESKTOP_BUNDLE__', {
  hermesCliProbe: () => ipcRenderer.invoke('ham-desktop:hermes-cli-probe'),
  runHermesPreset: (preset) => ipcRenderer.invoke('ham-desktop:hermes-preset', preset),
  readCuratedFile: (name) => ipcRenderer.invoke('ham-desktop:read-curated-file', name),
  openHermesUpstreamDocs: () => ipcRenderer.invoke('ham-desktop:open-hermes-upstream-docs'),
  localControl: localControlBridge,
});
