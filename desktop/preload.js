// Minimal privileged bridge. The window loads the token-gated dashboard SPA (its own same-origin
// fetch/SSE to the broker); contextIsolation + sandbox stay on. Two things the renderer can't do on
// its own: know whether the panel is parked (to render the count spine), and pin the sidebar open
// (toggle auto-hide). Both go through the main process here.
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('smbosPanel', {
  // Subscribe to collapse/expand; returns an unsubscribe fn. The renderer shows the rail when collapsed.
  onCollapsed: (cb) => {
    const handler = (_e, collapsed) => cb(!!collapsed)
    ipcRenderer.on('panel-collapsed', handler)
    return () => ipcRenderer.removeListener('panel-collapsed', handler)
  },
  // Pin the sidebar open (true = stay out, no auto-hide) / release it (false = auto-hide resumes).
  setPinned: (v) => ipcRenderer.send('panel-set-pinned', !!v),
  // Subscribe to the pinned state so the pin button reflects it; returns an unsubscribe fn.
  onPinned: (cb) => {
    const handler = (_e, pinned) => cb(!!pinned)
    ipcRenderer.on('panel-pinned', handler)
    return () => ipcRenderer.removeListener('panel-pinned', handler)
  },
})
