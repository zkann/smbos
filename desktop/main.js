// SmbOS desktop shell (Electron) -- Phase 1 of the strangler-fig switchover.
//
// This wraps the EXISTING live dashboard: it resolves the running FastAPI server's URL + token the
// same way the rest of the app does (the SOP dir's triggers.json port + .dashboard-token), opens it
// in a real desktop window, and adds a cross-platform tray + native notifications. The Python engine
// and the FastAPI server are untouched -- this is the thinnest wrap, so nothing about the working
// do-loop changes. Later phases stand up the Node broker and take over the server lifecycle.
//
// URL/token resolution is reimplemented in Node (rather than shelling to Python) so the shell has no
// Python dependency just to find the dashboard. It mirrors smbos_lib.dashboard_url / dashboard_port /
// dashboard_token: $SMBOS_DASHBOARD_PORT, else triggers.json dashboard_port, else 8765; token from
// <sop_dir>/.dashboard-token; sop_dir from $SOP_DIR, else ~/sops.

const { app, BrowserWindow, Tray, Menu, Notification, nativeImage } = require('electron')
const path = require('path')
const http = require('http')
const { dashboardPort, token, sopDir } = require('./resolve')
const { createBroker } = require('./broker')

const POLL_MS = 5000          // tray/notification poll cadence (matches the live mirror's calm cadence)

let win = null
let tray = null
let lastPlateCount = null  // null until the first successful poll, so we don't notify on startup
let broker = null
let brokerPort = null      // the broker's bound port; the window + poll talk to the broker, not FastAPI

// The renderer and the tray poll go through the BROKER (Phase 2), which forwards to FastAPI. The
// token is still FastAPI's; the broker passes ?t= and the header token straight through.
function brokerUrl(pathname = '/') {
  const u = new URL(`http://127.0.0.1:${brokerPort}${pathname}`)
  u.searchParams.set('t', token())  // set, not append, so a pathname with its own query stays valid
  return u.toString()
}

function createWindow() {
  if (win) { win.show(); win.focus(); return }
  win = new BrowserWindow({
    width: 480,
    height: 860,
    title: 'SmbOS',
    backgroundColor: '#09090b',  // the dashboard's --background, so there's no white flash on load
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  win.loadURL(brokerUrl('/'))
  win.on('closed', () => { win = null })  // keep the app alive in the tray when the window closes
}

// GET a token-gated JSON endpoint through the broker. Resolves null on any failure (server down, bad
// JSON) so a transient outage never crashes the poll loop.
function apiGet(pathname) {
  return new Promise((resolve) => {
    const req = http.get(brokerUrl(pathname), (res) => {
      let body = ''
      res.on('data', (c) => { body += c })
      res.on('end', () => { try { resolve(JSON.parse(body)) } catch (_) { resolve(null) } })
    })
    req.on('error', () => resolve(null))
    req.setTimeout(4000, () => { req.destroy(); resolve(null) })
  })
}

function updateTray(label, tip) {
  if (!tray) return
  tray.setTitle(label ? ` ${label}` : '')  // a small count next to the menu-bar icon, blank at zero
  tray.setToolTip(tip)
}

// Poll the plate: drive the tray count and fire a native notification when a NEW item lands (the
// count rose since the last poll). Quiet at zero and on startup. This is the off-dashboard loop (R4):
// the owner learns something needs them without watching the window.
async function pollPlate() {
  const d = await apiGet('/api/plate')
  const plate = d && Array.isArray(d.plate) ? d.plate : null
  if (plate == null) {
    updateTray('', 'SmbOS (dashboard not reachable)')
    return
  }
  const n = plate.length
  updateTray(n ? String(n) : '', n ? `${n} waiting for you` : 'SmbOS: nothing waiting')
  if (lastPlateCount != null && n > lastPlateCount && Notification.isSupported()) {
    const newest = plate[0]
    const note = new Notification({
      title: 'SmbOS: waiting for you',
      body: (newest && newest.subject) || `${n} on your plate`,
      silent: false,
    })
    note.on('click', createWindow)
    note.show()
  }
  lastPlateCount = n
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, 'assets', 'iconTemplate.png'))
  icon.setTemplateImage(true)  // macOS tints a template image for light/dark menu bars
  tray = new Tray(icon)
  tray.setToolTip('SmbOS')
  tray.on('click', createWindow)
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open dashboard', click: createWindow },
    { label: 'Reload', click: () => { if (win) win.loadURL(brokerUrl('/')) } },
    { type: 'separator' },
    { label: 'Quit SmbOS', click: () => app.quit() },
  ]))
}

app.whenReady().then(() => {
  // Start the broker (Phase 2 facade) in front of the running FastAPI dashboard, on a free loopback
  // port, then point everything at the broker. The broker forwards to FastAPI for now.
  broker = createBroker({ targetPort: dashboardPort(), sopDir: sopDir() })
  // A bind failure (EACCES/EADDRNOTAVAIL on loopback) would otherwise leave the listen callback
  // unfired -- no window, no tray, a resident process with no UI. Fail loud and quit instead.
  broker.on('error', (e) => {
    console.error('SmbOS broker failed to start:', (e && e.message) || e)
    app.quit()
  })
  broker.listen(0, '127.0.0.1', () => {
    brokerPort = broker.address().port
    createWindow()
    createTray()
    pollPlate()
    setInterval(pollPlate, POLL_MS)
  })
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})

// A tray app stays resident when its window closes (don't quit on window-all-closed). Quit only via
// the tray menu / Cmd-Q.
app.on('window-all-closed', () => { /* intentionally keep running in the tray */ })

// Release the broker's port on quit so a restart can re-bind cleanly.
app.on('will-quit', () => { if (broker) { broker.close(); broker = null } })
