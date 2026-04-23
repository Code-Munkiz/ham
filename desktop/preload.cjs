'use strict';

const { contextBridge, ipcRenderer } = require('electron');

const config = ipcRenderer.sendSync('ham-desktop:get-config-sync');

contextBridge.exposeInMainWorld('__HAM_DESKTOP_CONFIG__', config && typeof config === 'object' ? config : {});
