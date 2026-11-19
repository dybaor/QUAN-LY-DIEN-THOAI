const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ogkDesktop', {
    searchGoogle: query => ipcRenderer.invoke('ogk:google-search', query),
    closeGoogle: () => ipcRenderer.send('ogk:google-close'),
});
