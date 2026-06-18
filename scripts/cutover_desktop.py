#!/usr/bin/env python3
"""Cut the always-on console over from the FastAPI dashboard to the Electron + Node broker.

The broker now owns the whole surface (the SPA, every read, the SSE live mirror, all actions,
settings), so the Electron app -- which runs the broker on the dashboard port -- fully replaces
the FastAPI server. This flip points the login item at the Electron app, stops the FastAPI
server and the Python tray (the Electron app brings its own window + tray), and health-checks
the broker on the same port before trusting it. A failed check rolls straight back to FastAPI,
so a broken cutover never leaves the owner without a console.

Unlike the FastAPI cutover there is NO venv: the broker runs under Electron's bundled Node
(>=22.5 for node:sqlite) and the engine it invokes is stdlib system python3. The only build
step is the npm install + the SPA bundle. This module stays stdlib-only.

Rollback is one command: `cutover_desktop.py rollback` (or `uninstall`) reloads the FastAPI
plist (kept in place, never deleted) and removes the desktop agent.
"""
import plistlib
import subprocess
import sys
from pathlib import Path

import smbos_lib as lib           # dashboard_port() -- the canonical resolver
import serve_dashboard as legacy  # AGENT_LABEL (FastAPI), plist_path(), resolve_sop_dir() (the use_cwd wrapper)
import cutover_dashboard as fa    # reuse the launchctl + health plumbing (no need to duplicate it)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DESKTOP = PLUGIN_ROOT / "desktop"
FRONTEND = PLUGIN_ROOT / "frontend"
ELECTRON_BIN = DESKTOP / "node_modules" / ".bin" / "electron"

DESKTOP_LABEL = "com.smbos.desktop"   # the Electron app's own login item (NOT the FastAPI label)
TRAY_LABEL = "com.smbos.tray"         # the Python menu-bar tray the Electron tray replaces


def desktop_plist_path():
    return Path.home() / "Library" / "LaunchAgents" / (DESKTOP_LABEL + ".plist")


def _plist_path_for(label):
    return Path.home() / "Library" / "LaunchAgents" / (label + ".plist")


def desktop_plist_xml(sop_dir, port, electron_bin=ELECTRON_BIN):
    """LaunchAgent for the Electron app. Runs `electron <desktop/>` with the broker bound to the
    dashboard port (SMBOS_BROKER_PORT), so the window, the browser bookmark, and the engine's
    Run-button children all keep working on the same URL. RunAtLoad opens it at login; KeepAlive
    only restarts on a CRASH (SuccessfulExit:false), so quitting from the tray actually quits.

    WorkingDirectory stays the sop_dir (matching the FastAPI agent): folder-less SOP runs inherit
    it. PATH gets the usual install dirs so the broker-spawned engine resolves claude/git/npm."""
    log = str(Path(sop_dir) / "desktop.log")
    spec = {
        "Label": DESKTOP_LABEL,
        "ProgramArguments": [str(electron_bin), str(DESKTOP)],
        "WorkingDirectory": str(sop_dir),
        "EnvironmentVariables": {
            "SOP_DIR": str(sop_dir),
            "SMBOS_BROKER_PORT": str(port),       # the port the broker BINDS
            "SMBOS_DASHBOARD_PORT": str(port),    # and the port it resolves as targetPort, so the
                                                  # self-loop guard (targetPort == own port) fires --
                                                  # pin BOTH from one resolved port, never two sources
            "PATH": fa._launchd_path(electron_bin),
        },
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},  # respawn a crash, but let a clean tray-Quit stick
        "ThrottleInterval": 5,
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }
    return plistlib.dumps(spec).decode("utf-8")


def env_ready():
    """True when the Electron app can run without a (re)build: the electron binary is installed
    and the SPA bundle is built. (The broker itself is stdlib Node + node:sqlite; the engine is
    stdlib system python3 -- neither needs a build.)"""
    return ELECTRON_BIN.exists() and (FRONTEND / "dist" / "index.html").exists()


def build_env():
    """Install the desktop + frontend npm deps and build the SPA bundle. Idempotent."""
    steps = [
        ["npm", "ci", "--prefix", str(DESKTOP)],
        ["npm", "ci", "--prefix", str(FRONTEND)],
        ["npm", "run", "build", "--prefix", str(FRONTEND)],
    ]
    for cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return False, "{} failed: {}".format(" ".join(cmd[:3]), (r.stderr or r.stdout).strip()[:400])
    if not ELECTRON_BIN.exists():
        return False, "electron did not install at {}".format(ELECTRON_BIN)
    if not (FRONTEND / "dist" / "index.html").exists():
        return False, "SPA build produced no dist/index.html"
    return True, "desktop environment built"


def _disable_label(label):
    """Stop AND persistently disable a LaunchAgent (unload -w sets Disabled), so it can't RunAtLoad
    again at the next login and race the desktop agent for the port (EADDRINUSE). The plist FILE
    stays on disk for rollback; only the enabled-state flips. Idempotent."""
    plist = _plist_path_for(label)
    if not plist.exists():
        return
    fa._launchctl("unload", "-w", plist)


def _reload_label(label):
    """Re-enable + reload a LaunchAgent by label if its plist exists, then kickstart it up (load -w
    clears the Disabled flag _disable_label set). Best-effort."""
    plist = _plist_path_for(label)
    if not plist.exists():
        return
    fa._launchctl("load", "-w", plist)
    fa._kickstart(label)


def _restore_fastapi(sop_dir, port):
    """Bring the FastAPI dashboard + Python tray + their keep-alive cron back (re-enable the agents
    that _disable_label disabled, reinstall the watchdog migrate removed). Returns True if the port
    came back up. Shared by the auto-rollback and the manual rollback/uninstall."""
    fa._launchctl("unload", "-w", desktop_plist_path())
    try:
        desktop_plist_path().unlink()
    except OSError:
        pass
    _reload_label(legacy.AGENT_LABEL)   # FastAPI back on the port
    _reload_label(TRAY_LABEL)           # the Python tray back
    fa.install_watchdog(sop_dir)        # the keep-alive cron migrate removed
    return fa.wait_port_busy(port)


def _rollback(sop_dir, why, port):
    """Restore FastAPI after a failed flip, then report the failure. The cardinal sin is leaving the
    console dark, so we verify the port came back rather than assume."""
    if _restore_fastapi(sop_dir, port):
        return False, "{}; rolled back to the FastAPI dashboard on {}".format(why, port)
    return False, ("{}; ROLLBACK INCOMPLETE: the console on {} may be down. "
                   "Reload it with: launchctl load -w {}".format(why, port, legacy.plist_path()))


def migrate(sop_dir, port=None, electron_bin=ELECTRON_BIN):
    """Flip the login item from the FastAPI dashboard to the Electron app. Returns (ok, message).
    On any failure the FastAPI dashboard is restored, so the port is never left dark."""
    sop_dir = Path(sop_dir)
    if port is None:
        port = lib.dashboard_port(sop_dir)
    if not Path(electron_bin).exists():
        return False, "no electron binary at {} (run the build step first)".format(electron_bin)

    plist = desktop_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(desktop_plist_xml(sop_dir, port, electron_bin), encoding="utf-8")

    # Disable whatever holds the port + the redundant Python tray (the plists STAY on disk for
    # rollback; only the enabled-state flips, so they can't RunAtLoad and race the port at login).
    _disable_label(legacy.AGENT_LABEL)
    _disable_label(TRAY_LABEL)
    # Remove the FastAPI keep-alive cron: left in place it would kickstart com.smbos.dashboard back
    # onto this same port (a port fight), and resurrect FastAPI behind the user's back after a Quit.
    fa.remove_watchdog()
    if not fa.wait_port_free(port):
        return _rollback(sop_dir, "port {} never freed".format(port), port)
    r = fa._launchctl("load", "-w", plist)
    if r.returncode != 0:
        return _rollback(sop_dir, (r.stderr or "launchctl load failed").strip(), port)
    fa._kickstart(DESKTOP_LABEL)  # load alone leaves the job registered-but-not-running
    # A generous budget: an Electron cold start (process spawn + app.whenReady + broker.listen, plus
    # first-launch Gatekeeper/quarantine checks) is far slower than the python server this reuses --
    # too tight a window would roll back a healthy-but-slow app. ~30s.
    if not fa.health_ok(sop_dir, port, attempts=60):
        return _rollback(sop_dir, "the Electron broker did not answer on {}".format(port), port)
    return True, "cut over to the Electron + broker console on {}".format(port)


def rollback_to_fastapi(sop_dir):
    """Manual rollback: tear down the desktop agent and bring the FastAPI dashboard + tray + watchdog
    back (the same restore the auto-rollback uses)."""
    sop_dir = Path(sop_dir)
    port = lib.dashboard_port(sop_dir)
    if _restore_fastapi(sop_dir, port):
        return True, "rolled back to the FastAPI dashboard on {}".format(port)
    return False, "the FastAPI dashboard did not come back up on {}; reload: launchctl load -w {}".format(
        port, legacy.plist_path())


COMMANDS = {"build", "migrate", "install", "uninstall", "rollback"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = next((a for a in argv if a in COMMANDS), None)
    positional = [a for a in argv if a not in COMMANDS and not a.startswith("-")]
    sop_dir = (Path(positional[0]).expanduser().resolve() if positional
               else legacy.resolve_sop_dir())

    if cmd is None:
        sys.exit("usage: cutover_desktop.py [install|migrate|build|rollback|uninstall] [sop_dir]")
    if cmd in ("uninstall", "rollback"):
        ok, msg = rollback_to_fastapi(sop_dir)
        print(msg, flush=True)
        sys.exit(0 if ok else 1)
    if cmd == "build":
        ok, msg = build_env()
    elif cmd == "migrate":
        ok, msg = migrate(sop_dir)
    else:  # install: build only if needed, then flip
        if env_ready():
            ok, msg = True, "desktop environment already built"
        else:
            ok, msg = build_env()
        if ok:
            ok, msg = migrate(sop_dir)
    print(msg, flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
