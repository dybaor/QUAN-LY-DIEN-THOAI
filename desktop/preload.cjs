const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ogkDesktop', {
    searchGoogle: query => ipcRenderer.send('ogk:google-search', query),
    onSearchAttempt: callback => {
        ipcRenderer.on('ogk:google-search-attempt', (_event, query) => callback(query));
    },
    closeGoogle: () => ipcRenderer.send('ogk:google-close'),
});
