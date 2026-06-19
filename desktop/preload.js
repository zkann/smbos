// Minimal privileged bridge. The window loads the token-gated dashboard SPA (its own same-origin
// fetch/SSE to the broker); contextIsolation + sandbox stay on. The one thing the renderer can't know
// on its own is whether the desktop panel is parked (collapsed to the edge rail) vs slid out, so the
// main process signals it here and the SPA renders the count spine instead of the full dashboard.
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('smbosPanel', {
  // Subscribe to collapse/expand; returns an unsubscribe fn. The renderer shows the rail when collapsed.
  onCollapsed: (cb) => {
    const handler = (_e, collapsed) => cb(!!collapsed)
    ipcRenderer.on('panel-collapsed', handler)
    return () => ipcRenderer.removeListener('panel-collapsed', handler)
  },
})
