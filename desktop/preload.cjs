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
