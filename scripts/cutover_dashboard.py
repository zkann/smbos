#!/usr/bin/env python3
"""Cut the always-on dashboard over from the legacy stdlib daemon to the FastAPI app.

Strangler-fig: same launchd label (com.smbos.dashboard) and same port (8765), so the
bookmark and the login-item identity never change. We keep the prior plist text in hand
and health-check the new server before trusting it; a failed check rolls straight back to
the legacy daemon, so a broken cutover never leaves the owner without a dashboard.

The app depends on fastapi/uvicorn, so it runs under a venv interpreter (not the system
python the legacy daemon used). build_env() creates that venv and the SPA bundle; migrate()
does the flip. This module itself stays stdlib-only so it runs on the system python that
orchestrates the venv creation.
"""
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import serve_dashboard as legacy  # plist_path(), AGENT_LABEL, resolve_sop_dir()
import smbos_lib as lib           # dashboard_token()

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
APP = PLUGIN_ROOT / "scripts" / "dashboard_app.py"
FRONTEND = PLUGIN_ROOT / "frontend"
VENV = PLUGIN_ROOT / ".venv"   # the daemon's interpreter home
PORT = 8765                    # take over the legacy daemon's port


def venv_python(venv=VENV):
    return Path(venv) / "bin" / "python"


# --- the plist the cutover installs (repoints the legacy label at the app) -------------
def _launchd_path(python_exec):
    """launchd hands jobs a bare PATH; a Run-button child (claude, git, npm) would not be
    found. Prepend the usual install dirs and the venv bin so spawned runs resolve them."""
    home = Path.home()
    dirs = ["/opt/homebrew/bin", "/usr/local/bin", str(home / ".local" / "bin"),
            str(Path(python_exec).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return ":".join(dirs)


def app_plist_xml(sop_dir, python_exec, port=PORT):
    """LaunchAgent for the FastAPI app. Reuses the legacy label (we repoint it), runs the
    venv interpreter, and drops WatchPaths on purpose: the app holds a live SSE stream, so
    a watch-triggered restart would drop every connected browser on any file touch.

    WorkingDirectory stays the sop_dir (matching the legacy daemon): the app captures cwd
    once at startup and threads it into folder-less SOP runs, so PLUGIN_ROOT here would
    silently re-scope those runs."""
    log = str(Path(sop_dir) / "dashboard-app.log")
    spec = {
        "Label": legacy.AGENT_LABEL,
        "ProgramArguments": [str(python_exec), str(APP),
                             "--sop-dir", str(sop_dir), "--port", str(port)],
        "WorkingDirectory": str(sop_dir),
        "EnvironmentVariables": {"PATH": _launchd_path(python_exec)},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 5,
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }
    return plistlib.dumps(spec).decode("utf-8")


# --- health + readiness ----------------------------------------------------------------
def port_free(port=PORT, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def wait_port_free(port=PORT, attempts=20, delay=0.5):
    for _ in range(attempts):
        if port_free(port):
            return True
        time.sleep(delay)
    return False


def wait_port_busy(port=PORT, attempts=20, delay=0.5):
    """Inverse of wait_port_free: confirm something grabbed the port (used to verify a
    rolled-back legacy daemon actually came back up)."""
    for _ in range(attempts):
        if not port_free(port):
            return True
        time.sleep(delay)
    return False


def _get_200(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def health_ok(sop_dir, port=PORT, attempts=20, delay=0.5):
    """The app is healthy once BOTH /api/plate (API live) and / (SPA bundle served) answer
    200. Probing / too catches a built-but-bundle-missing app that would serve a blank page
    while the API still passes. The legacy daemon 404s on /api/plate, so it can't false-pass."""
    token = lib.dashboard_token(sop_dir)
    api = "http://127.0.0.1:{}/api/plate?t={}".format(port, token)
    root = "http://127.0.0.1:{}/?t={}".format(port, token)
    for _ in range(attempts):
        if _get_200(api) and _get_200(root):
            return True
        time.sleep(delay)
    return False


def _can_import(python_exec, modules):
    """True if `python_exec` can import the given comma-separated modules (from scripts/)."""
    r = subprocess.run([str(python_exec), "-c", "import " + modules],
                       cwd=str(PLUGIN_ROOT / "scripts"), capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "").strip()


def compat_ok(python_exec):
    """Pre-flight smoke test (not a full schema guarantee): confirm the venv interpreter can
    import the shared modules it'll run under the daemon. The venv and the system python both
    write the same stdlib-sqlite3 mirror via state_store, so an import failure is the likely
    breakage; this catches that before we hand the venv the daemon, not deeper schema skew."""
    return _can_import(python_exec, "sqlite3, state_store, smbos_lib")


# --- launchctl plumbing ----------------------------------------------------------------
def _launchctl(action, plist, *flags):
    return subprocess.run(["launchctl", action, *flags, str(plist)],
                          capture_output=True, text=True)


def _kickstart(label=None):
    """Force launchd to (re)spawn the job NOW. `launchctl load -w` immediately after an
    unload of the same label registers the job but does not reliably start the process, so
    every load in this flow is followed by a kickstart to actually bring the port up."""
    label = label or legacy.AGENT_LABEL
    return subprocess.run(
        ["launchctl", "kickstart", "-k", "gui/{}/{}".format(os.getuid(), label)],
        capture_output=True, text=True)


def _rollback(plist, prior, why, port=PORT):
    """Restore whatever ran under the label before we touched it, then report the failure.

    The cardinal sin is leaving the port dark, so we don't just claim recovery: we unload
    the failed app, reload the prior daemon, and confirm the load took (returncode) AND that
    something actually bound the port again. If either fails we say so loudly."""
    _launchctl("unload", plist)
    if prior is None:
        try:
            plist.unlink()
        except OSError:
            pass
        return False, "{}; no prior daemon to roll back to".format(why)
    plist.write_text(prior, encoding="utf-8")
    r = _launchctl("load", plist, "-w")
    if r.returncode == 0:
        # only after a clean load: kickstart -k on a failed/stale load could restart the bad
        # app job (it kills the running instance first) and leave the wrong server on the port.
        _kickstart()
        if wait_port_busy(port):
            return False, "{}; rolled back to the legacy daemon".format(why)
    return False, ("{}; ROLLBACK INCOMPLETE: the dashboard on {} may be down. "
                   "Reload it with: launchctl load -w {}".format(why, port, plist))


def migrate(sop_dir, python_exec=None, port=None):
    """Flip the label from the legacy daemon to the app. Returns (ok, message). On any
    failure the label is restored to exactly what ran before, so the port is never left dark.

    The port defaults to whatever the legacy daemon serves for this sop_dir (its configured
    dashboard_port, 8765 if unset), so an owner who moved the bookmark off 8765 keeps it."""
    sop_dir = Path(sop_dir)
    if port is None:
        port = legacy.dashboard_port(sop_dir)
    python_exec = Path(python_exec or venv_python())
    if not python_exec.exists():
        return False, "no venv interpreter at {} (run the build step first)".format(python_exec)
    ok, err = compat_ok(python_exec)
    if not ok:
        return False, "venv interpreter cannot import the shared modules: {}".format(err)

    plist = legacy.plist_path()
    prior = plist.read_text(encoding="utf-8") if plist.exists() else None
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(app_plist_xml(sop_dir, python_exec, port), encoding="utf-8")

    _launchctl("unload", plist)  # stop the legacy daemon holding the port (idempotent)
    if not wait_port_free(port):
        return _rollback(plist, prior, "port {} never freed".format(port), port)
    r = _launchctl("load", plist, "-w")
    if r.returncode != 0:
        return _rollback(plist, prior, (r.stderr or "launchctl load failed").strip(), port)
    _kickstart()  # load alone leaves the job registered-but-not-running; force it up
    if not health_ok(sop_dir, port):
        return _rollback(plist, prior, "new dashboard did not answer on {}".format(port), port)
    return True, "cut over to the FastAPI dashboard on {}".format(port)


# --- one-time environment build (slow, network-bound; not exercised by unit tests) ------
def build_env(venv=VENV):
    """Create the venv, install the app's deps, and build the SPA bundle. Idempotent."""
    venv = Path(venv)
    steps = [
        [sys.executable, "-m", "venv", str(venv)],
        [str(venv_python(venv)), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        [str(venv_python(venv)), "-m", "pip", "install", "--quiet",
         "-r", str(PLUGIN_ROOT / "requirements.txt")],
        ["npm", "ci", "--prefix", str(FRONTEND)],
        ["npm", "run", "build", "--prefix", str(FRONTEND)],
    ]
    for cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return False, "{} failed: {}".format(cmd[0], (r.stderr or r.stdout).strip()[:400])
    if not (FRONTEND / "dist" / "index.html").exists():
        return False, "SPA build produced no dist/index.html"
    # Best-effort: terminal-notifier lets a notification click open the dashboard (osascript
    # notifications can't, they open Script Editor). Never fail the build for it.
    if shutil.which("brew") and not shutil.which("terminal-notifier"):
        try:
            subprocess.run(["brew", "install", "terminal-notifier"], capture_output=True, timeout=300)
        except (OSError, subprocess.SubprocessError):
            pass
    return True, "environment built"


def env_ready(venv=VENV):
    """True when the app can run without a (re)build: venv interpreter present, SPA bundle
    built, and the interpreter imports BOTH the shared modules and the app's runtime deps
    (fastapi/uvicorn). The dep check matters: a half-built venv would pass compat_ok (stdlib
    only) yet crash the app on startup, so without it `install` would skip the build that's
    needed and then fail the cutover. Lets a ready machine skip the slow build_env."""
    py = venv_python(venv)
    if not py.exists() or not (FRONTEND / "dist" / "index.html").exists():
        return False
    return compat_ok(py)[0] and _can_import(py, "fastapi, uvicorn")[0]


COMMANDS = {"build", "migrate", "install", "uninstall", "url"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = next((a for a in argv if a in COMMANDS), None)
    positional = [a for a in argv if a not in COMMANDS and not a.startswith("-")]
    sop_dir = (Path(positional[0]).expanduser().resolve() if positional
               else legacy.resolve_sop_dir())

    if cmd is None:  # require an explicit verb: a bare path must not trigger a live flip
        sys.exit("usage: cutover_dashboard.py [install|migrate|build|url|uninstall] [sop_dir]")
    if cmd == "url":
        print(legacy.stable_url(sop_dir))
        return
    if cmd == "uninstall":
        ok = legacy.uninstall_agent()
        print("Always-on dashboard removed." if ok else "No always-on dashboard was installed.")
        return
    if cmd == "build":
        ok, msg = build_env()
    elif cmd == "migrate":
        ok, msg = migrate(sop_dir)
    else:  # install (also the default): build only if needed, then flip
        if env_ready():
            ok, msg = True, "environment already built"
        else:
            ok, msg = build_env()
        if ok:
            ok, msg = migrate(sop_dir)
        if ok:
            print("Always-on dashboard installed. It starts at login and serves a stable URL "
                  "(bookmark it):", flush=True)
            print(legacy.stable_url(sop_dir))
            return
    print(msg, flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
