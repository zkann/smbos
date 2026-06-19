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

const { app, BrowserWindow, Tray, Menu, Notification, nativeImage, screen, globalShortcut, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')
const http = require('http')
const { dashboardPort, token, sopDir } = require('./resolve')
const { createBroker } = require('./broker')

const POLL_MS = 5000          // tray/notification poll cadence (matches the live mirror's calm cadence)
const DOCK_WIDTH = 400        // sidebar width when docked + slid out (~standard sidebar footprint)
const TAB_W = 52              // parked tab: a compact frosted pill at the edge (vs the full DOCK_WIDTH panel)
const TAB_H = 104             // parked tab height, vertically centered on the docked display
const FLOAT_SIZE = { width: 480, height: 860 }  // the normal (undocked) floating window
const TOGGLE_HOTKEY = 'Control+Command+S'  // global summon/dismiss; ^⌘S is rarely a system/app global
const SLIDE_MS = 140          // edge slide duration
const SLIDE_STEPS = 9         // frames per slide (ease-out)
const HIDE_GRACE_MS = 450     // wait after the cursor leaves before parking (no flicker on a brief mouse-out)
const EDGE_POLL_MS = 110      // how often the cursor is checked for an edge-reveal

let win = null
let tray = null
let lastPlateCount = null  // null until the first successful poll, so we don't notify on startup
let broker = null
let brokerPort = null      // the broker's bound port; the window + poll talk to the broker, not FastAPI
let docked = true          // sidebar mode: right-edge, always-on-top, all-Spaces (the default the user asked for)
let autoHide = true        // (docked only) park off the edge and slide out on edge-hover / hotkey
let panelOut = true        // is the panel currently slid out (vs parked off-screen)
let pinned = false         // hotkey/tray force-open: stay out, ignore the auto-hide poll
let slideTimer = null      // the slide animation interval
let hideTimer = null       // the post-mouse-out grace timer
let edgeTimer = null       // the cursor-edge poll interval
let dockDisplayId = null   // the display we docked on, so geometry can't drift onto a neighbour monitor

// Persist the dock + auto-hide choices across restarts (userData is the standard per-app store).
function prefsFile() { return path.join(app.getPath('userData'), 'window-prefs.json') }
function loadPrefs() {
  try {
    const p = JSON.parse(fs.readFileSync(prefsFile(), 'utf8'))
    if (p && typeof p.docked === 'boolean') docked = p.docked
    if (p && typeof p.autoHide === 'boolean') autoHide = p.autoHide
  } catch (_) { /* no prefs yet: keep the defaults */ }
}
function savePrefs() {
  try { fs.writeFileSync(prefsFile(), JSON.stringify({ docked, autoHide })) } catch (_) { /* best-effort */ }
}

// The renderer and the tray poll go through the BROKER (Phase 2), which forwards to FastAPI. The
// token is still FastAPI's; the broker passes ?t= and the header token straight through.
function brokerUrl(pathname = '/') {
  const u = new URL(`http://127.0.0.1:${brokerPort}${pathname}`)
  u.searchParams.set('t', token())  // set, not append, so a pathname with its own query stays valid
  return u.toString()
}

// The URL the WINDOW loads: panel=1 when docked so the dashboard goes translucent for the native
// vibrancy. The undocked window + the API polls use the plain brokerUrl (opaque).
function windowUrl() { return brokerUrl('/') + (docked ? '&panel=1' : '') }

// --- geometry on the REMEMBERED docked display (not the window's live display, which can drift onto
//     a neighbour after parking, and not the cursor's). Falls back to the window's / primary display
//     if the docked one was unplugged. ---------------------------------------------------------------
function dockDisplay() {
  const all = screen.getAllDisplays()
  let d = all.find((x) => x.id === dockDisplayId)
  if (!d) { d = win ? screen.getDisplayMatching(win.getBounds()) : screen.getPrimaryDisplay(); dockDisplayId = d.id }
  return d
}
function dockArea() { return dockDisplay().workArea }
function outX(a) { return a.x + a.width - DOCK_WIDTH }  // the panel's slid-out x (its left edge)
function panelBounds(a) { return { x: outX(a), y: a.y, width: DOCK_WIDTH, height: a.height } }
// The parked tab: a small pill at the right edge, vertically centered on the docked display.
function tabBounds(a) {
  return { x: a.x + a.width - TAB_W, y: a.y + Math.round((a.height - TAB_H) / 2), width: TAB_W, height: TAB_H }
}

// Tell the renderer to show the count spine (collapsed) vs the full dashboard. De-duped so the poll
// can't spam IPC; reset per window so the first signal always lands.
let collapsedSent = null
function sendCollapsed(v) {
  if (collapsedSent === v) return
  collapsedSent = v
  if (win && !win.isDestroyed() && win.webContents) win.webContents.send('panel-collapsed', v)
}
// Tell the renderer whether the sidebar is pinned open (auto-hide off), so the pin button reflects it.
function sendPinned() {
  if (win && !win.isDestroyed() && win.webContents) win.webContents.send('panel-pinned', !autoHide)
}
function outerRightEdge() { return Math.max(...screen.getAllDisplays().map((d) => d.workArea.x + d.workArea.width)) }
// Sliding 'off the right edge' only goes off-SCREEN when the docked display is the rightmost; with a
// monitor to its right, the parked tab would land on the neighbour. So edge-reveal/auto-hide only arms
// on the rightmost display -- elsewhere the panel stays pinned out (visible) rather than silently broken.
function edgeHideable() { const a = dockArea(); return a.x + a.width >= outerRightEdge() - 1 }
function effectiveAutoHide() { return autoHide && edgeHideable() }

// Slide the window's x to `target` over SLIDE_MS (ease-out), cancelling any in-flight slide.
function slideX(target, onDone) {
  if (!win) return
  if (slideTimer) { clearInterval(slideTimer); slideTimer = null }
  const start = win.getBounds().x, delta = target - start
  if (delta === 0) { if (onDone) onDone(); return }
  let i = 0
  slideTimer = setInterval(() => {
    if (!win) { clearInterval(slideTimer); slideTimer = null; return }
    i++
    const ease = 1 - Math.pow(1 - i / SLIDE_STEPS, 2)
    const b = win.getBounds()
    win.setBounds({ x: Math.round(start + delta * ease), y: b.y, width: b.width, height: b.height })
    if (i >= SLIDE_STEPS) { clearInterval(slideTimer); slideTimer = null; if (onDone) onDone() }
  }, Math.max(8, Math.round(SLIDE_MS / SLIDE_STEPS)))
}

function revealPanel() {
  if (!win) return
  const a = dockArea()
  if (panelOut && win.getBounds().width === DOCK_WIDTH) {  // already the full panel: just ensure shown
    sendCollapsed(false)
    if (!win.isVisible()) win.show()
    return
  }
  // From the tab: snap to the full panel parked just off the right edge (the tab vanishes, off-screen),
  // then slide the full-size dashboard in. Resizing here, not mid-slide, avoids a cramped reflow.
  panelOut = true
  sendCollapsed(false)
  win.setBounds({ ...panelBounds(a), x: a.x + a.width })
  if (!win.isVisible()) win.show()
  slideX(outX(a))
}
function parkPanel() {
  if (!win || pinned || !panelOut) return  // idempotent: don't re-park an already-parked tab
  const a = dockArea()
  panelOut = false
  slideX(a.x + a.width, () => {   // slide the full panel off the right edge...
    if (!win || panelOut) return  // (a reveal raced us)
    sendCollapsed(true)
    win.setBounds(tabBounds(a))   // ...then shrink to the small tab, centered at the edge
  })
}
function schedulePark() { if (!hideTimer) hideTimer = setTimeout(() => { hideTimer = null; parkPanel() }, HIDE_GRACE_MS) }
function cancelPark() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null } }

// The edge watch: reveal when the cursor is at the docked display's right edge (or over the slid-out
// panel), re-park a beat after it leaves. Runs only while docked + (effective) auto-hide + not pinned.
function pollEdge() {
  if (!win || !docked || !effectiveAutoHide() || pinned) return
  const a = dockArea(), p = screen.getCursorScreenPoint()
  const inY = p.y >= a.y && p.y <= a.y + a.height
  const atEdge = inY && p.x >= a.x + a.width - 1
  const overPanel = panelOut && inY && p.x >= outX(a) - 6
  if (atEdge || overPanel) { cancelPark(); if (!panelOut) revealPanel() }
  else if (panelOut) schedulePark()
}
function startEdgeWatch() { if (!edgeTimer) edgeTimer = setInterval(pollEdge, EDGE_POLL_MS) }
function stopEdgeWatch() { if (edgeTimer) { clearInterval(edgeTimer); edgeTimer = null } }

// Apply the current dock + auto-hide state to the live window.
function applyDockState() {
  if (!win) return
  cancelPark()
  if (docked) {
    win.setAlwaysOnTop(true, 'floating')
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    dockDisplayId = screen.getDisplayMatching(win.getBounds()).id  // remember the screen we dock on
    const a = dockArea()
    win.setBounds(panelBounds(a))  // start visible/docked (full panel out)
    if (effectiveAutoHide()) {
      pinned = false
      panelOut = true     // shown first so the user sees where it docked; the poll parks it on mouse-away
      startEdgeWatch()
    } else {
      stopEdgeWatch()
      pinned = true       // not auto-hiding (off, or a non-rightmost display): it simply stays out
      panelOut = true
    }
  } else {
    stopEdgeWatch()
    win.setAlwaysOnTop(false)
    win.setVisibleOnAllWorkspaces(false)
    win.setSize(FLOAT_SIZE.width, FLOAT_SIZE.height)
    win.center()
  }
  sendCollapsed(false)  // applyDockState always leaves the panel OUT (full dashboard), so un-collapse
                        // the renderer -- e.g. toggling auto-hide off while parked must drop the rail
}

function setDocked(next) {
  docked = next
  savePrefs()
  // frame + type:'panel' are fixed at creation, so flipping modes REBUILDS the window: docked -> a
  // chromeless NSPanel sidebar, undocked -> a normal framed window (own z-order, one Space).
  if (win) { win.destroy(); win = null }
  createWindow()
  refreshTrayMenu()
}

function setAutoHide(next) {
  autoHide = next
  savePrefs()
  applyDockState()  // start/stop the edge watch + re-park or pin-out
  refreshTrayMenu()
  sendPinned()      // keep the in-panel pin button in sync (pinned = auto-hide off)
}

function createWindow() {
  if (win) { applyDockState(); summon(); return }
  win = new BrowserWindow({
    ...FLOAT_SIZE,
    title: 'SmbOS',
    // Docked = a CHROMELESS macOS NSPanel (floats over full-screen apps, all Spaces, no focus-steal).
    // transparent + square (roundedCorners:false): the window is a fully transparent square rect, so
    // the FROST is done in CSS (backdrop-filter), clipped to the rounded tab / panel shape -- no
    // window-level vibrancy rectangle showing behind the rounded tab. Undocked = a normal opaque window.
    ...(docked
      ? { type: 'panel', frame: false, roundedCorners: false, transparent: true, backgroundColor: '#00000000' }
      : { backgroundColor: '#09090b' }),  // opaque so there's no white flash on load
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  collapsedSent = null  // fresh window: let the first collapse/expand signal land
  win.loadURL(windowUrl())
  // The renderer can miss an IPC sent before it loaded, so (re)send the current collapse state once
  // the page is up.
  win.webContents.on('did-finish-load', () => { collapsedSent = null; sendCollapsed(!panelOut); sendPinned() })
  win.on('closed', () => { win = null; stopEdgeWatch(); cancelPark() })  // keep the app alive in the tray
  // Close on blur: clicking to another window tucks the auto-hide panel away -- the same "it goes away
  // when I'm done with it" the edge-reveal gives on cursor-leave, now also for a tray/hotkey summon
  // (which focuses the panel, so switching windows fires this).
  win.on('blur', () => { if (docked && effectiveAutoHide()) { pinned = false; parkPanel() } })
  applyDockState()  // honor the persisted dock/auto-hide choice on open
}

// Bring the panel out for a DELIBERATE open (tray / notification / hotkey). Pins it so the cursor poll
// won't tuck it while you reach for it, and focuses it so clicking another window closes it (blur).
function summon() {
  if (!win) { createWindow(); return }
  if (docked && effectiveAutoHide()) { pinned = true; cancelPark(); revealPanel(); win.focus() }
  else { win.show(); win.focus() }
}

// The global hotkey: summon if parked, dismiss if already out. In auto-hide mode "dismiss" resumes
// the slide-away; in the plain modes it hides/shows the window.
function toggleWindowVisible() {
  if (!win) { createWindow(); return }
  if (docked && effectiveAutoHide()) {
    if (pinned || panelOut) { pinned = false; parkPanel() }  // dismiss -> tuck away, auto-hide resumes
    else summon()                                            // reveal + focus (closes on blur / dismiss)
  } else if (win.isVisible()) win.hide()
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
    note.on('click', summon)  // clicking the notification brings the panel out and keeps it
    note.show()
  }
  lastPlateCount = n
}

function refreshTrayMenu() {
  if (!tray) return
  const items = [
    { label: 'Open dashboard', click: summon },
    // one item that reflects + flips the state (don't strand the user in one mode)
    docked
      ? { label: 'Undock (floating window)', click: () => setDocked(false) }
      : { label: 'Dock to right edge', click: () => setDocked(true) },
  ]
  if (docked) {
    items.push({ label: 'Auto-hide at edge', type: 'checkbox', checked: autoHide, click: () => setAutoHide(!autoHide) })
  }
  items.push(
    { label: `Show / hide (${TOGGLE_HOTKEY.replace('Control+Command+', '⌃⌘')})`, click: toggleWindowVisible },
    { label: 'Reload', click: () => { if (win) win.loadURL(windowUrl()) } },
    { type: 'separator' },
    { label: 'Quit SmbOS', click: () => app.quit() },
  )
  tray.setContextMenu(Menu.buildFromTemplate(items))
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, 'assets', 'iconTemplate.png'))
  icon.setTemplateImage(true)  // macOS tints a template image for light/dark menu bars
  tray = new Tray(icon)
  tray.setToolTip('SmbOS')
  tray.on('click', summon)
  refreshTrayMenu()
}

app.whenReady().then(() => {
  // Menu-bar utility: no Dock icon, not in ⌘-Tab (reach it via the tray, ⌃⌘S, or the screen edge),
  // matching native edge-panel apps like SidePeek. Guarded for non-macOS where app.dock is absent.
  if (app.dock) app.dock.hide()
  // The in-panel pin button toggles auto-hide (pinned open = auto-hide off).
  ipcMain.on('panel-set-pinned', (_e, pinnedOpen) => setAutoHide(!pinnedOpen))
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
    // Re-pin when the display layout changes (resolution change / a monitor plugged or unplugged), so
    // the docked panel can't be stranded off-screen, and re-arm or disarm auto-hide if the docked
    // display stopped/started being the rightmost.
    const repin = () => {
      if (!docked || !win) return
      const a = dockArea()
      if (effectiveAutoHide()) {
        startEdgeWatch()
        win.setBounds(panelOut ? panelBounds(a) : tabBounds(a))  // re-fit the panel or the tab
      } else {
        stopEdgeWatch()
        pinned = true
        panelOut = true
        sendCollapsed(false)
        win.setBounds(panelBounds(a))
      }
    }
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
