#!/usr/bin/env python3
"""SmbOS menu-bar tray: a glanceable status item over the always-on dashboard daemon.

This is the lightest cross-platform-deferred shell (a macOS rumps status item), a thin
CLIENT of the existing FastAPI daemon, not an owner of it. The daemon (com.smbos.dashboard)
keeps serving /api + /events and stays always-on; the tray only polls it and opens it. That
split is deliberate: the daemon fires notifications and holds the live mirror even when no
window is open, so the tray adds presence without taking over lifecycle.

Design (locked in /plan-design-review against DESIGN.md "Command Center"):

  BADGE STATE MODEL                          MENU (house vocabulary, no jargon)
  loading      -> "·"   (don't flash a 0)    SmbOS                  (identity / trunk test)
  zero waiting -> "○"   (DESIGN.md:22        ----
                         zero is neutral,    3 waiting for you  ->  opens dashboard
                         never tinted)       1 in flight        ->  opens dashboard
  N waiting    -> "● N"  (the glance signal,  2 coming up        ->  opens dashboard
                          N is plate count)   ----
  disconnected -> "⚠"   (attention without   Open dashboard
                         color; see note)    ----
                                             Restart dashboard  (was "Restart daemon")
  EMPTY:  "Nothing waiting for you right now."   Quit SmbOS
  DOWN:   "Dashboard isn't running" / "Start it"

Color note: a text status-item title cannot be per-glyph colored, so DESIGN.md's "muted red
dot" for the lost-connection state is rendered as the ⚠ glyph instead. Glyph-not-color also
satisfies the design review's "never signal by color alone" a11y point. A template-image icon
(SF Symbol) could restore the tinted dot later; that is DT-followup polish, not prototype work.

Structure: the rumps import is GUARDED and all rumps usage lives in main()/TrayApp, so the
pure logic (fetch_counts, compute_state, badge_title, menu_model, plist) imports and tests
under the macOS system Python 3.9 with no third-party deps, matching the repo's test pattern.
Only `main()` (the running app) needs rumps, which lives in the dashboard's .venv.
"""
import json
import os
import plistlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ on path for imports
import serve_dashboard as daemon  # stable_url, live_server_url, dashboard_port, AGENT_LABEL
import smbos_lib as lib           # dashboard_token, resolve_sop_dir

try:
    import rumps  # third-party (pyobjc); only the running app needs it
except ImportError:  # pragma: no cover - tests exercise the pure logic without rumps
    rumps = None

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
APP = PLUGIN_ROOT / "scripts" / "tray_app.py"
VENV_PYTHON = PLUGIN_ROOT / ".venv" / "bin" / "python"
TRAY_LABEL = "com.smbos.tray"          # distinct from the daemon's com.smbos.dashboard
# A minimal .app bundle so macOS shows "SmbOS" (name + icon) in the Accessibility prompt,
# System Settings, and notifications, instead of "Python". The bundle's executable IS the venv
# interpreter (symlinked), so launching from inside it makes NSBundle.mainBundle() resolve to
# SmbOS.app; the venv's packages reach it via PYTHONPATH (set in the LaunchAgent). Kept out of
# the repo (built at install time, references machine-absolute paths).
APP_BUNDLE = Path.home() / "Library" / "Application Support" / "SmbOS" / "SmbOS.app"
SERVER_FILE = ".dashboard-server.json"  # the daemon records its ACTUAL bound port/token here
POLL_SECONDS = 5                        # badge freshness; polling beats holding an SSE stream
                                        # in a menu-bar process (simpler, plenty responsive)
PANEL_WIDTH = 360                       # the side panel's width (right edge)
HANDLE_WIDTH = 6                        # the thin always-visible peek handle at the edge
PEEK_EDGE_PX = 2                        # cursor within this of the right edge summons the drawer
PEEK_HYSTERESIS = 12                    # px left of the panel before it auto-hides (anti-flicker)

# Panel modes. HIDDEN: badge only. PEEK (default): a thin handle on the edge; the drawer slides
# in on edge-hover and auto-hides (overlay, no space reserved). DOCKED: parked open AND the
# neighbor window is reflowed (Accessibility) so nothing draws under it, a true sidebar.
MODE_HIDDEN, MODE_PEEK, MODE_DOCKED = "hidden", "peek", "docked"

# Badge glyphs. Filled = work waiting, hollow = clear, dot = loading, warning = down.
# The number rides only on the filled glyph, so the badge APPEARING is itself the signal.
GLYPH_LOADING = "·"
GLYPH_IDLE = "○"
GLYPH_WORK = "●"
GLYPH_DOWN = "⚠"


# --- data: poll the daemon for the three plate buckets -----------------------------------
def _server(sop_dir):
    """The daemon's ACTUAL (port, token): prefer its recorded server file (covers a fallback
    port and a rotated token), else the stable defaults. Reusing the daemon's own record keeps
    the tray correct without re-deriving anything it already wrote."""
    rec = Path(sop_dir) / SERVER_FILE
    try:
        info = json.loads(rec.read_text(encoding="utf-8"))
        return int(info["port"]), str(info["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return daemon.dashboard_port(sop_dir), lib.dashboard_token(sop_dir)


def _get_json(url, opener=urllib.request.urlopen):
    with opener(url, timeout=2) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_counts(sop_dir, opener=urllib.request.urlopen):
    """The three bucket counts as {'waiting','inflight','coming'}, or None when the daemon is
    not reachable. None is the disconnected signal; any connection/HTTP error maps to it so a
    daemon that is not up yet (e.g. just after login) degrades quietly instead of raising."""
    port, token = _server(sop_dir)
    base = "http://127.0.0.1:{}".format(port)
    q = lambda path, key: len(_get_json("{}{}?t={}".format(base, path, token), opener)[key])
    try:
        return {
            "waiting": q("/api/plate", "plate"),
            "inflight": q("/api/inflight", "inflight"),
            "coming": q("/api/queue", "queue"),
        }
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


# --- pure view logic (rumps-free, fully unit-testable) -----------------------------------
def compute_state(counts):
    """Normalize fetch_counts() output into a render state. counts is None (down), or the
    three-bucket dict (ok)."""
    if counts is None:
        return {"status": "down"}
    return {
        "status": "ok",
        "waiting": int(counts.get("waiting", 0)),
        "inflight": int(counts.get("inflight", 0)),
        "coming": int(counts.get("coming", 0)),
    }


def badge_title(state):
    """The menu-bar title for a state. Honors zero-is-neutral: the count shows ONLY when
    something waits, so a quiet hollow glyph is the resting state (D2: icon-only at zero)."""
    if state is None:
        return GLYPH_LOADING
    if state.get("status") == "down":
        return GLYPH_DOWN
    waiting = state.get("waiting", 0)
    if waiting > 0:
        return "{} {}".format(GLYPH_WORK, waiting)
    return GLYPH_IDLE


# The real mark is an SF Symbol monogram (native, template-tinted, dark/light aware). The
# fill encodes state so the brand "S" still reads work-vs-clear at a glance; the down state
# drops the monogram for an unmistakable warning, the one place clarity beats brand.
SYMBOL_IDLE = "s.square"             # outline S: quiet, neutral resting state (D2)
SYMBOL_WORK = "s.square.fill"        # filled S: work is waiting
SYMBOL_DOWN = "exclamationmark.triangle.fill"


def symbol_name(state):
    """The SF Symbol for a state (pure; the running app renders it as a template image)."""
    if state is None:
        return SYMBOL_IDLE
    if state.get("status") == "down":
        return SYMBOL_DOWN
    return SYMBOL_WORK if state.get("waiting", 0) > 0 else SYMBOL_IDLE


def count_text(state):
    """The number that rides beside the icon: the waiting count, or '' when there's none to
    show (zero/loading/down). Keeps zero-is-neutral, the icon alone carries the resting state."""
    if state and state.get("status") == "ok" and state.get("waiting", 0) > 0:
        return str(state["waiting"])
    return ""


def accessibility_label(state):
    """A spoken-words label for VoiceOver, so the badge is never number/color-only
    (DESIGN.md:22 generalized: status always ships with a text label)."""
    if state is None:
        return "SmbOS, loading"
    if state.get("status") == "down":
        return "SmbOS, dashboard not running"
    w = state.get("waiting", 0)
    if w == 0:
        return "SmbOS, nothing waiting for you"
    return "SmbOS, {} waiting for you".format(w)


def _plural(n, noun):
    return "{} {}".format(n, noun)


# --- panel geometry + peek triggers (pure, unit-tested) ----------------------------------
def panel_rect(vx, vy, vw, vh, width=PANEL_WIDTH):
    """The docked panel frame (right edge, full visible height). vx/vy/vw/vh = visibleFrame."""
    return (vx + vw - width, vy, width, vh)


def handle_rect(vx, vy, vw, vh, width=HANDLE_WIDTH):
    """The thin always-visible peek handle, flush to the right edge, full height."""
    return (vx + vw - width, vy, width, vh)


def peek_should_show(mx, vx, vw, edge_px=PEEK_EDGE_PX):
    """Summon the drawer when the cursor reaches the right screen edge (you can always slam the
    pointer to the edge, so a 2px target is reliable; the visible handle just marks where)."""
    return mx >= (vx + vw - edge_px)


def peek_should_hide(mx, vx, vw, width=PANEL_WIDTH, hysteresis=PEEK_HYSTERESIS):
    """Auto-hide once the cursor moves left of the open drawer (hysteresis stops edge flicker)."""
    return mx < (vx + vw - width - hysteresis)


def fit_width(win_x, win_w, vx, vw, panel_width=PANEL_WIDTH, min_width=320):
    """The width a neighbor window should shrink to so its right edge clears the docked panel,
    or None if it already fits. x-only, so the AX top-left/Cocoa bottom-left mismatch is moot."""
    limit_right = vx + vw - panel_width
    if win_x + win_w <= limit_right:
        return None
    return max(min_width, limit_right - win_x)


# --- menu ---------------------------------------------------------------------------------
def _panel_items(panel_mode):
    """The panel controls for the current mode, or [] when no app is running (pure tests call
    menu_model without a mode). Each mode offers the transitions that make sense from it."""
    if panel_mode is None:
        return []
    if panel_mode == MODE_HIDDEN:
        return [{"title": "Show panel", "action": "panel_peek", "enabled": True}]
    if panel_mode == MODE_DOCKED:
        return [{"title": "Undock panel", "action": "panel_peek", "enabled": True},
                {"title": "Hide panel", "action": "panel_hide", "enabled": True}]
    # PEEK (default)
    return [{"title": "Dock as sidebar", "action": "panel_dock", "enabled": True},
            {"title": "Hide panel", "action": "panel_hide", "enabled": True}]


def menu_model(state, panel_mode=None):
    """The dropdown as a list of item specs (pure data; main() renders it with rumps).

    Each item is a dict: {"sep": True} for a separator, else {"title", "action", "enabled"}.
    actions: None (info), "open", "restart", "start", "quit", and the panel-mode transitions
    "panel_peek"/"panel_dock"/"panel_hide". The breakdown lines surface the plate vocabulary;
    clicking any opens the dashboard. panel_mode (None off-app) drives the panel controls."""
    items = [{"title": "SmbOS", "action": None, "enabled": False}, {"sep": True}]
    panel = _panel_items(panel_mode)

    if state is not None and state.get("status") == "down":
        # Failure copy: what happened, then the one fix (DESIGN.md voice).
        items += [
            {"title": "Dashboard isn't running", "action": None, "enabled": False},
            {"title": "Start it", "action": "start", "enabled": True},
            {"sep": True},
        ]
        items += panel  # still let the user move/hide a panel showing a dead dashboard
        if panel:
            items.append({"sep": True})
        items.append({"title": "Quit SmbOS", "action": "quit", "enabled": True})
        return items

    # Connected (or loading, treated as connected-but-empty until the first poll lands).
    waiting = state.get("waiting", 0) if state else 0
    inflight = state.get("inflight", 0) if state else 0
    coming = state.get("coming", 0) if state else 0

    rows = []
    if waiting:
        rows.append({"title": _plural(waiting, "waiting for you"), "action": "open", "enabled": True})
    if inflight:
        rows.append({"title": _plural(inflight, "in flight"), "action": "open", "enabled": True})
    if coming:
        rows.append({"title": _plural(coming, "coming up"), "action": "open", "enabled": True})
    if not rows:  # truly nothing across all three buckets: the dashboard's own empty copy
        rows.append({"title": "Nothing waiting for you right now.", "action": None, "enabled": False})

    tail = [{"sep": True}] + panel + [
        {"title": "Open dashboard", "action": "open", "enabled": True},
        {"sep": True},
        {"title": "Restart dashboard", "action": "restart", "enabled": True},
        {"title": "Quit SmbOS", "action": "quit", "enabled": True},
    ]
    items += rows + tail
    return items


# --- actions -----------------------------------------------------------------------------
def dashboard_url(sop_dir):
    """The dashboard URL to load (browser or panel). Prefer the daemon's live (actual) URL so
    a fallback port still works; fall back to the stable URL."""
    return daemon.live_server_url(sop_dir) or daemon.stable_url(sop_dir)


def open_dashboard(sop_dir):
    """Open the full dashboard in the default browser (the deep surface)."""
    subprocess.run(["open", dashboard_url(sop_dir)], capture_output=True)


def restart_daemon():
    """Kickstart the daemon job. launchctl kickstart -k respawns it now (the same recovery the
    cutover uses); this is the menu's manual fix for the daemon-down / stale states."""
    uid = os.getuid()
    return subprocess.run(
        ["launchctl", "kickstart", "-k", "gui/{}/{}".format(uid, daemon.AGENT_LABEL)],
        capture_output=True, text=True,
    )


# --- the .app bundle: give the process the "SmbOS" name in notifications and the app menu ---
# A minimal bundle whose executable is a symlink to the venv interpreter. NSBundle resolves to
# SmbOS.app, so notifications and the menu read "SmbOS". NOTE: the macOS Accessibility prompt
# (for "Dock as sidebar") still shows the Python interpreter's name, TCC won't trust an unsigned
# / ad-hoc bundle and follows the interpreter; naming it there would need Developer ID signing +
# notarization, which is out of scope for a local single-user tool.
def bundle_exec(bundle=APP_BUNDLE):
    return Path(bundle) / "Contents" / "MacOS" / "SmbOS"


def venv_site_packages(python_exec=None):
    """The venv's site-packages dir, put on the LaunchAgent's PYTHONPATH so the symlinked
    interpreter finds rumps/pyobjc (the bundle exec is a symlink, so venv auto-detection is off)."""
    python_exec = str(python_exec or VENV_PYTHON)
    r = subprocess.run(
        [python_exec, "-c", "import sys;print(next(p for p in sys.path if 'site-packages' in p))"],
        capture_output=True, text=True)
    return r.stdout.strip()


def build_app_bundle(python_exec=None, bundle=APP_BUNDLE):
    """Create SmbOS.app: an Info.plist (name/identity) and a MacOS/SmbOS executable that symlinks
    the venv interpreter. Launching from inside it makes NSBundle resolve to SmbOS.app, so the app
    name reads 'SmbOS' in notifications and the menu. Idempotent. Returns the executable path."""
    python_exec = Path(python_exec or VENV_PYTHON)
    bundle = Path(bundle)
    (bundle / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    (bundle / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleName": "SmbOS",
        "CFBundleDisplayName": "SmbOS",
        "CFBundleIdentifier": TRAY_LABEL,
        "CFBundleExecutable": "SmbOS",
        "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "LSUIElement": True,  # status-bar app, no Dock icon
    }))
    exe = bundle_exec(bundle)
    try:
        exe.unlink()
    except OSError:
        pass
    exe.symlink_to(python_exec)  # the bundle's executable IS the interpreter
    return exe


# --- launchd: run the tray at login, alongside (not owning) the daemon -------------------
def _launchd_path():
    home = Path.home()
    dirs = ["/opt/homebrew/bin", "/usr/local/bin", str(home / ".local" / "bin"),
            str(VENV_PYTHON.parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return ":".join(dirs)


def tray_plist_xml(sop_dir, exe=None, pythonpath=None):
    """LaunchAgent for the tray. Launches the bundle's executable (the symlinked interpreter, so
    the process is named 'SmbOS') with the script and --sop-dir, and the venv's site-packages on
    PYTHONPATH so the symlink finds its deps. RunAtLoad gives login durability (KeepAlive respawn
    is unreliable on Darwin 25, so login-start is the real story); KeepAlive matches the daemon."""
    exe = str(exe or bundle_exec())
    env = {"PATH": _launchd_path()}
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    log = str(Path(sop_dir) / "tray.log")
    spec = {
        "Label": TRAY_LABEL,
        "ProgramArguments": [exe, str(APP), "--sop-dir", str(sop_dir)],
        "EnvironmentVariables": env,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 5,
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }
    return plistlib.dumps(spec).decode("utf-8")


def tray_plist_path():
    return Path.home() / "Library" / "LaunchAgents" / (TRAY_LABEL + ".plist")


def install_agent(sop_dir, python_exec=None):
    exe = build_app_bundle(python_exec)           # the SmbOS.app wrapper (names notifications)
    pythonpath = venv_site_packages(python_exec)  # so the symlinked interpreter finds its deps
    plist = tray_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(tray_plist_xml(sop_dir, exe, pythonpath), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    r = subprocess.run(["launchctl", "load", "-w", str(plist)], capture_output=True, text=True)
    if r.returncode == 0:
        subprocess.run(["launchctl", "kickstart", "-k",
                        "gui/{}/{}".format(os.getuid(), TRAY_LABEL)], capture_output=True)
    return r.returncode == 0, (r.stderr or "").strip()


def uninstall_agent():
    plist = tray_plist_path()
    existed = plist.exists()
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    subprocess.run(["launchctl", "bootout", "gui/{}/{}".format(os.getuid(), TRAY_LABEL)],
                   capture_output=True)
    try:
        plist.unlink()
    except OSError:
        pass
    shutil.rmtree(APP_BUNDLE.parent, ignore_errors=True)  # remove the built .app
    return existed


# --- the running app (rumps; only reached in main()) -------------------------------------
def _set_accessibility(app, label):
    """Best-effort VoiceOver label on the status-item button. Reaches into the AppKit object
    rumps holds; wrapped because the private attr is not part of rumps's public API."""
    try:
        button = app._nsapp.nsstatusitem.button()  # type: ignore[attr-defined]
        button.setAccessibilityLabel_(label)
    except Exception:
        pass


def _build():
    """Construct the TrayApp class. Deferred into a function so importing this module never
    requires rumps (the class subclasses rumps.App)."""

    class TrayApp(rumps.App):
        def __init__(self, sop_dir):
            super().__init__("SmbOS", title=GLYPH_LOADING, quit_button=None)
            self.sop_dir = sop_dir
            self.state = None
            self._panel = None       # the drawer (WKWebView)
            self._webview = None
            self._handle = None      # the thin always-visible peek handle
            self._monitor = None     # global mouse-moved monitor (drives peek)
            self._peek_open = False  # is the drawer slid in right now (peek mode)
            self._mode = MODE_HIDDEN
            self._docked = []        # [(ax_window, orig_w, orig_h)] to restore on undock
            self._ws_token = None    # workspace activation observer (re-reflow on app switch)
            self.render()
            rumps.Timer(self._tick, POLL_SECONDS).start()
            self.set_mode(MODE_PEEK)  # default: handle on the edge, drawer on hover

        # one poll -> recompute state -> repaint badge + menu
        def _tick(self, _timer):
            self.state = compute_state(fetch_counts(self.sop_dir))
            self.render()

        def render(self):
            self._paint(symbol_name(self.state), count_text(self.state), badge_title(self.state))
            _set_accessibility(self, accessibility_label(self.state))
            self.menu.clear()
            for spec in menu_model(self.state, self._mode):
                if spec.get("sep"):
                    self.menu.add(rumps.separator)
                    continue
                item = rumps.MenuItem(spec["title"], callback=self._dispatch(spec["action"]))
                self.menu.add(item)

        def _paint(self, sym, count, fallback_text):
            """Paint the status item: SF Symbol monogram (template) + the count beside it.
            Falls back to the text glyph if the symbol can't be made (older macOS / no button),
            so the badge always shows SOMETHING rather than going blank."""
            button = None
            img = None
            try:
                from AppKit import NSImage
                button = self._nsapp.nsstatusitem.button()
                img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(sym, None)
            except Exception:
                pass
            if button is not None and img is not None:
                from AppKit import NSImageLeft, NSImageOnly
                img.setTemplate_(True)
                button.setImage_(img)
                button.setImagePosition_(NSImageLeft if count else NSImageOnly)
                self.title = " " + count if count else ""
            else:
                self.title = fallback_text  # text-glyph fallback

        def _dispatch(self, action):
            if action is None:
                return None  # info row: rumps renders a callback-less item as disabled
            return {
                "open": lambda _: open_dashboard(self.sop_dir),
                "restart": lambda _: restart_daemon(),
                "start": lambda _: restart_daemon(),
                "panel_peek": lambda _: self.set_mode(MODE_PEEK),
                "panel_dock": lambda _: self.set_mode(MODE_DOCKED),
                "panel_hide": lambda _: self.set_mode(MODE_HIDDEN),
                "quit": lambda _: rumps.quit_application(),
            }[action]

        # --- the side panel: peek drawer (overlay) <-> docked sidebar (reflows neighbor) -----
        # PEEK floats a non-activating WKWebView over your other apps WITHOUT stealing focus;
        # a thin handle marks the edge and the drawer slides in on hover, auto-hiding so it
        # never permanently blocks an app. DOCKED parks it open AND shrinks the neighbor window
        # (Accessibility) so nothing is covered. Every AppKit/AX step is guarded: a panel
        # failure must never take down the badge, the tray's core job.
        def set_mode(self, mode):
            try:
                if self._mode == MODE_DOCKED and mode != MODE_DOCKED:
                    self._undock()
                if mode == MODE_HIDDEN:
                    self._stop_monitor(); self._drawer_hide(); self._handle_hide()
                    self._peek_open = False
                elif mode == MODE_PEEK:
                    self._handle_show(); self._drawer_hide(); self._peek_open = False
                    self._start_monitor()
                elif mode == MODE_DOCKED:
                    self._stop_monitor(); self._handle_hide()
                    self._drawer_show(); self._peek_open = True
                    if not self._dock():  # AX denied: keep the drawer but restore peek behavior
                        mode = MODE_PEEK
                        self._handle_show(); self._start_monitor()
            except Exception:
                pass
            self._mode = mode
            self.render()  # refresh the menu's panel controls for the new mode

        # drawer (the WKWebView panel) -------------------------------------------------
        def _ensure_panel(self):
            if self._panel is not None:
                return self._panel
            from AppKit import (
                NSPanel, NSScreen, NSBackingStoreBuffered,
                NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
                NSFloatingWindowLevel, NSViewWidthSizable, NSViewHeightSizable,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
            )
            from Foundation import NSMakeRect
            from WebKit import WKWebView, WKWebViewConfiguration

            vis = NSScreen.mainScreen().visibleFrame()
            x, y, w, h = panel_rect(vis.origin.x, vis.origin.y, vis.size.width, vis.size.height)
            style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, w, h), style, NSBackingStoreBuffered, False)
            panel.setLevel_(NSFloatingWindowLevel)
            panel.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorStationary
                | NSWindowCollectionBehaviorFullScreenAuxiliary)
            panel.setHidesOnDeactivate_(False)
            panel.setReleasedWhenClosed_(False)
            panel.setBecomesKeyOnlyIfNeeded_(True)  # clicks act, but focus stays put
            webview = WKWebView.alloc().initWithFrame_configuration_(
                NSMakeRect(0, 0, w, h), WKWebViewConfiguration.alloc().init())
            webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            panel.setContentView_(webview)
            self._panel, self._webview = panel, webview
            return panel

        def _drawer_show(self):
            try:
                panel = self._ensure_panel()
                from Foundation import NSURL, NSURLRequest
                url = NSURL.URLWithString_(dashboard_url(self.sop_dir))
                self._webview.loadRequest_(NSURLRequest.requestWithURL_(url))
                panel.orderFrontRegardless()  # show WITHOUT activating (focus stays put)
            except Exception:
                pass

        def _drawer_hide(self):
            try:
                if self._panel is not None:
                    self._panel.orderOut_(None)
            except Exception:
                pass

        # handle (the thin edge marker) ------------------------------------------------
        def _ensure_handle(self):
            if self._handle is not None:
                return self._handle
            from AppKit import (NSPanel, NSScreen, NSColor, NSBackingStoreBuffered,
                                 NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
                                 NSFloatingWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces,
                                 NSWindowCollectionBehaviorStationary,
                                 NSWindowCollectionBehaviorFullScreenAuxiliary)
            from Foundation import NSMakeRect
            vis = NSScreen.mainScreen().visibleFrame()
            x, y, w, h = handle_rect(vis.origin.x, vis.origin.y, vis.size.width, vis.size.height)
            style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
            handle = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, w, h), style, NSBackingStoreBuffered, False)
            handle.setLevel_(NSFloatingWindowLevel)
            handle.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorStationary
                | NSWindowCollectionBehaviorFullScreenAuxiliary)
            handle.setOpaque_(False)
            handle.setIgnoresMouseEvents_(True)  # marker only; the global monitor drives peek
            handle.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.55, 0.5))
            self._handle = handle
            return handle

        def _handle_show(self):
            try:
                self._ensure_handle().orderFrontRegardless()
            except Exception:
                pass

        def _handle_hide(self):
            try:
                if self._handle is not None:
                    self._handle.orderOut_(None)
            except Exception:
                pass

        # peek: a global mouse monitor slides the drawer in at the edge, out past it --------
        def _start_monitor(self):
            if self._monitor is not None:
                return
            try:
                from AppKit import NSEvent, NSEventMaskMouseMoved
                self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                    NSEventMaskMouseMoved, lambda e: self._on_mouse_move())
            except Exception:
                self._monitor = None

        def _stop_monitor(self):
            try:
                if self._monitor is not None:
                    from AppKit import NSEvent
                    NSEvent.removeMonitor_(self._monitor)
            except Exception:
                pass
            self._monitor = None

        def _on_mouse_move(self):
            if self._mode != MODE_PEEK:
                return
            try:
                from AppKit import NSEvent, NSScreen
                loc = NSEvent.mouseLocation()
                vis = NSScreen.mainScreen().visibleFrame()
                vx, vw = vis.origin.x, vis.size.width
                if not self._peek_open and peek_should_show(loc.x, vx, vw):
                    self._peek_open = True
                    self._handle_hide(); self._drawer_show()
                elif self._peek_open and peek_should_hide(loc.x, vx, vw):
                    self._peek_open = False
                    self._drawer_hide(); self._handle_show()
            except Exception:
                pass

        # dock: reserve real space by reflowing the neighbor window (Accessibility) ---------
        def _dock(self):
            """Reflow the neighbor window so it clears the panel. Returns False (caller falls
            back to peek) when Accessibility isn't granted, so the drawer still auto-hides."""
            if not _ax_trusted():
                _prompt_ax()  # surface the system permission prompt
                rumps.notification("SmbOS", "Dock needs Accessibility",
                                   "Allow SmbOS in System Settings > Privacy & Security > "
                                   "Accessibility, then choose Dock as sidebar again.")
                return False
            self._reflow_active_window()
            self._subscribe_activation()
            return True

        def _undock(self):
            try:
                if self._ws_token is not None:
                    from AppKit import NSWorkspace
                    NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self._ws_token)
            except Exception:
                pass
            self._ws_token = None
            for win, w, h in list(self._docked):  # restore the EXACT windows we shrank
                self._set_window_size(win, w, h)
            self._docked = []

        def _subscribe_activation(self):
            try:
                from AppKit import NSWorkspace, NSWorkspaceDidActivateApplicationNotification
                nc = NSWorkspace.sharedWorkspace().notificationCenter()
                if self._ws_token is not None:  # never stack observers (re-dock would leak one)
                    nc.removeObserver_(self._ws_token)
                self._ws_token = nc.addObserverForName_object_queue_usingBlock_(
                    NSWorkspaceDidActivateApplicationNotification, None, None,
                    lambda _n: self._reflow_active_window())
            except Exception:
                self._ws_token = None

        def _reflow_active_window(self):
            """Shrink the frontmost window so it clears the panel, and remember the exact element
            + its original size so undock restores it (not whatever is focused at undock time).
            Single primary display: off-main windows are skipped (the x/width math assumes main)."""
            try:
                from AppKit import NSWorkspace, NSScreen
                from ApplicationServices import (
                    AXUIElementCreateApplication, AXUIElementCopyAttributeValue,
                    kAXFocusedWindowAttribute, kAXPositionAttribute, kAXSizeAttribute,
                    AXValueGetValue, kAXValueTypeCGPoint, kAXValueTypeCGSize)
                front = NSWorkspace.sharedWorkspace().frontmostApplication()
                if front is None or front.processIdentifier() == os.getpid():
                    return
                appel = AXUIElementCreateApplication(front.processIdentifier())
                err, win = AXUIElementCopyAttributeValue(appel, kAXFocusedWindowAttribute, None)
                if err != 0 or win is None:
                    return
                ep, posv = AXUIElementCopyAttributeValue(win, kAXPositionAttribute, None)
                es, szv = AXUIElementCopyAttributeValue(win, kAXSizeAttribute, None)
                if ep != 0 or es != 0 or posv is None or szv is None:
                    return
                _, pos = AXValueGetValue(posv, kAXValueTypeCGPoint, None)
                _, sz = AXValueGetValue(szv, kAXValueTypeCGSize, None)
                vis = NSScreen.mainScreen().visibleFrame()
                if pos.x < vis.origin.x or pos.x >= vis.origin.x + vis.size.width:
                    return  # window is on another display; single-screen math doesn't apply
                new_w = fit_width(pos.x, sz.width, vis.origin.x, vis.size.width)
                if new_w is None:
                    return  # already clears the panel (or we already shrank it: no double-store)
                self._docked.append((win, sz.width, sz.height))  # the exact element to restore
                self._set_window_size(win, new_w, sz.height)
            except Exception:
                pass

        def _set_window_size(self, win, w, h):
            """Set an AX window element's size directly (operates on the saved element, so undock
            restores the window we actually shrank even after the focus has moved)."""
            try:
                from ApplicationServices import (
                    AXUIElementSetAttributeValue, kAXSizeAttribute, AXValueCreate, kAXValueTypeCGSize)
                from Quartz import CGSize
                AXUIElementSetAttributeValue(
                    win, kAXSizeAttribute, AXValueCreate(kAXValueTypeCGSize, CGSize(w, h)))
            except Exception:
                pass

    return TrayApp


def _ax_trusted():
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _prompt_ax():
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = next((a for a in argv if a in {"install", "uninstall"}), None)
    positional = [a for a in argv if a not in {"install", "uninstall"} and not a.startswith("-")]
    if "--sop-dir" in argv:
        sop_dir = Path(argv[argv.index("--sop-dir") + 1]).expanduser().resolve()
    elif positional:
        sop_dir = Path(positional[0]).expanduser().resolve()
    else:
        sop_dir = daemon.resolve_sop_dir()

    if cmd == "install":
        ok, msg = install_agent(sop_dir)
        print("SmbOS menu-bar tray installed (starts at login)." if ok
              else "Install failed: {}".format(msg))
        sys.exit(0 if ok else 1)
    if cmd == "uninstall":
        print("Menu-bar tray removed." if uninstall_agent() else "No menu-bar tray was installed.")
        return

    if rumps is None:
        sys.exit("rumps is not installed. Install the dashboard env, then: "
                 "{} -m pip install rumps".format(VENV_PYTHON))
    _build()(sop_dir).run()


if __name__ == "__main__":
    main()
