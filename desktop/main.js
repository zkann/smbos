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

const { app, BrowserWindow, Tray, Menu, Notification, nativeImage, screen, globalShortcut } = require('electron')
const path = require('path')
const fs = require('fs')
const http = require('http')
const { dashboardPort, token, sopDir } = require('./resolve')
const { createBroker } = require('./broker')

const POLL_MS = 5000          // tray/notification poll cadence (matches the live mirror's calm cadence)
const DOCK_WIDTH = 400        // sidebar width when docked to a screen edge (~standard sidebar footprint)
const FLOAT_SIZE = { width: 480, height: 860 }  // the normal (undocked) floating window
const TOGGLE_HOTKEY = 'Control+Command+S'  // global show/hide; ^⌘S is rarely a system/app global

let win = null
let tray = null
let lastPlateCount = null  // null until the first successful poll, so we don't notify on startup
let broker = null
let brokerPort = null      // the broker's bound port; the window + poll talk to the broker, not FastAPI
let docked = true          // sidebar mode: right-edge, always-on-top, all-Spaces (the default the user asked for)

// Persist the dock choice across restarts (userData is the standard per-app store).
function prefsFile() { return path.join(app.getPath('userData'), 'window-prefs.json') }
function loadPrefs() {
  try {
    const p = JSON.parse(fs.readFileSync(prefsFile(), 'utf8'))
    if (p && typeof p.docked === 'boolean') docked = p.docked
  } catch (_) { /* no prefs yet: keep the default (docked) */ }
}
function savePrefs() {
  try { fs.writeFileSync(prefsFile(), JSON.stringify({ docked })) } catch (_) { /* best-effort */ }
}

// The renderer and the tray poll go through the BROKER (Phase 2), which forwards to FastAPI. The
// token is still FastAPI's; the broker passes ?t= and the header token straight through.
function brokerUrl(pathname = '/') {
  const u = new URL(`http://127.0.0.1:${brokerPort}${pathname}`)
  u.searchParams.set('t', token())  // set, not append, so a pathname with its own query stays valid
  return u.toString()
}

// Pin the window to the right edge of the window's CURRENT display, full work-area height. Keying off
// the window (not the cursor) keeps a re-pin after a display change from flinging it to whichever
// screen the pointer happens to be on, and clamps to the nearest remaining display if one is unplugged.
function dockToRightEdge() {
  if (!win) return
  const area = screen.getDisplayMatching(win.getBounds()).workArea
  win.setBounds({ x: area.x + area.width - DOCK_WIDTH, y: area.y, width: DOCK_WIDTH, height: area.height })
}

// Apply the current dock state to the live window. Docked = an edge-pinned sidebar that floats over
// other windows and rides along to every Space; undocked = a normal floating window. (The NSPanel
// `type: 'panel'` -- set at creation -- is what lets it sit over full-screen apps without stealing
// focus from your editor either way.)
function applyDockState() {
  if (!win) return
  const wasVisible = win.isVisible()  // toggling flags/geometry must not surface a deliberately-hidden panel
  if (docked) {
    win.setAlwaysOnTop(true, 'floating')
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    dockToRightEdge()
  } else {
    win.setAlwaysOnTop(false)
    win.setVisibleOnAllWorkspaces(false)
    win.setSize(FLOAT_SIZE.width, FLOAT_SIZE.height)
    win.center()
  }
  if (!wasVisible && win.isVisible()) win.hide()  // setAlwaysOnTop(false) can resurface a hidden window
}

function setDocked(next) {
  docked = next
  savePrefs()
  // type:'panel' is fixed at window creation, so flipping modes REBUILDS the window rather than just
  // repositioning the same panel: docked -> an NSPanel sidebar, undocked -> a normal activating window
  // (its own z-order, one Space). createWindow reads `docked` for the type and applies the geometry.
  if (win) { win.destroy(); win = null }
  createWindow()
  refreshTrayMenu()
}

function createWindow() {
  // a panel is non-activating, so show() (not focus) is the right nudge; re-apply the dock state first
  // so "Open dashboard" always normalizes geometry (e.g. after a display change while hidden)
  if (win) { applyDockState(); win.show(); return }
  win = new BrowserWindow({
    ...FLOAT_SIZE,
    title: 'SmbOS',
    // macOS NSPanel only when docked: floats over full-screen apps, all Spaces, no focus-steal.
    // Undocked rebuilds WITHOUT it, so it's a normal activating window (own z-order, one Space).
    ...(docked ? { type: 'panel' } : {}),
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
  applyDockState()  // honor the persisted dock/float choice on every (re)open
}

// Auto-hide convention: the global hotkey shows the panel if hidden, hides it if already showing.
function toggleWindowVisible() {
  if (!win) { createWindow(); return }
  if (win.isVisible()) win.hide()
  else win.show()
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

function refreshTrayMenu() {
  if (!tray) return
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open dashboard', click: createWindow },
    // one item that reflects + flips the state (don't strand the user in one mode)
    docked
      ? { label: 'Undock (floating window)', click: () => setDocked(false) }
      : { label: 'Dock to right edge', click: () => setDocked(true) },
    { label: `Show / hide (${TOGGLE_HOTKEY.replace('Control+Command+', '⌃⌘')})`, click: toggleWindowVisible },
    { label: 'Reload', click: () => { if (win) win.loadURL(brokerUrl('/')) } },
    { type: 'separator' },
    { label: 'Quit SmbOS', click: () => app.quit() },
  ]))
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, 'assets', 'iconTemplate.png'))
  icon.setTemplateImage(true)  // macOS tints a template image for light/dark menu bars
  tray = new Tray(icon)
  tray.setToolTip('SmbOS')
  tray.on('click', createWindow)
  refreshTrayMenu()
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
  // Bind port: $SMBOS_BROKER_PORT (the cutover sets this to the dashboard port so the broker takes
  // over 8765 -- the window, the browser bookmark, and the tray's open-browser all keep working),
  // else 0 for a free loopback port (dev / a second instance).
  const wantPort = Number(process.env.SMBOS_BROKER_PORT)
  const bindPort = Number.isInteger(wantPort) && wantPort >= 0 && wantPort <= 65535 ? wantPort : 0
  broker.listen(bindPort, '127.0.0.1', () => {
    brokerPort = broker.address().port
    loadPrefs()        // restore the dock/float choice before the window opens
    createWindow()
    createTray()
    // Global show/hide (the auto-hide convention). Best-effort: a registration clash just means no
    // hotkey, not a crash -- the tray item does the same thing.
    if (!globalShortcut.register(TOGGLE_HOTKEY, toggleWindowVisible)) {
      console.error(`SmbOS: could not register the ${TOGGLE_HOTKEY} hotkey (in use); use the tray instead`)
    }
    // Re-pin to the edge when the display layout changes (resolution change / a monitor unplugged),
    // so the docked panel can't be stranded off-screen.
    const repin = () => { if (docked) dockToRightEdge() }
    screen.on('display-metrics-changed', repin)
    screen.on('display-removed', repin)
    screen.on('display-added', repin)
    pollPlate()
    setInterval(pollPlate, POLL_MS)
  })
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})

// A tray app stays resident when its window closes (don't quit on window-all-closed). Quit only via
// the tray menu / Cmd-Q.
app.on('window-all-closed', () => { /* intentionally keep running in the tray */ })

// Release the broker's port + the global hotkey on quit so a restart can re-bind cleanly.
app.on('will-quit', () => {
  globalShortcut.unregisterAll()
  if (broker) { broker.close(); broker = null }
})
