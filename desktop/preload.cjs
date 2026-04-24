'use strict';

const { contextBridge, ipcRenderer } = require('electron');

const config = ipcRenderer.sendSync('ham-desktop:get-config-sync');

contextBridge.exposeInMainWorld('__HAM_DESKTOP_CONFIG__', config && typeof config === 'object' ? config : {});

contextBridge.exposeInMainWorld('__HAM_DESKTOP_BUNDLE__', {
  hermesCliProbe: () => ipcRenderer.invoke('ham-desktop:hermes-cli-probe'),
  runHermesPreset: (preset) => ipcRenderer.invoke('ham-desktop:hermes-preset', preset),
  readCuratedFile: (name) => ipcRenderer.invoke('ham-desktop:read-curated-file', name),
  openHermesUpstreamDocs: () => ipcRenderer.invoke('ham-desktop:open-hermes-upstream-docs'),
});
