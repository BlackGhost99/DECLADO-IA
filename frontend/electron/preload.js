const { contextBridge, ipcRenderer } = require('electron');

/**
 * Preload script - Expose des APIs sécurisées au renderer process
 */

contextBridge.exposeInMainWorld('electronAPI', {
  // Obtenir l'URL du backend
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  
  // Vérifier le statut du backend
  checkBackendStatus: () => ipcRenderer.invoke('check-backend-status'),
  
  // Informations de l'application
  platform: process.platform,
  versions: {
    node: process.versions.node,
    chrome: process.versions.chrome,
    electron: process.versions.electron,
  },
});
