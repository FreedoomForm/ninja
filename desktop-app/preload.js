const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getStatus: () => ipcRenderer.invoke('get-status'),
  getConfig: () => ipcRenderer.invoke('get-config'),
  saveConfig: (config) => ipcRenderer.invoke('save-config', config),
  startBot: () => ipcRenderer.invoke('start-bot'),
  stopBot: () => ipcRenderer.invoke('stop-bot'),
  getLogs: () => ipcRenderer.invoke('get-logs'),
  clearLogs: () => ipcRenderer.invoke('clear-logs'),
  startBackend: () => ipcRenderer.invoke('start-backend'),
  checkBackend: () => ipcRenderer.invoke('check-backend')
});
