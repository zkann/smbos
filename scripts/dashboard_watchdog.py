#!/usr/bin/env python3
"""Keep the always-on dashboard up when launchd won't.

On some macOS versions launchd does not honor a user LaunchAgent's RunAtLoad / KeepAlive /
StartInterval, so the dashboard never starts after a crash or a reboot. Run from cron, this
checks the dashboard's configured port and kickstarts the LaunchAgent when it's down
(kickstart first; bootstrap-then-kickstart as a fallback for the case where the agent isn't
loaded yet, e.g. just after boot). Stdlib only: it runs under the system python from cron.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smbos_lib as lib           # dashboard_port, resolve_sop_dir
import serve_dashboard as legacy  # AGENT_LABEL, plist_path


def port_up(port, host="127.0.0.1", timeout=1.0):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _wait_up(port, attempts=8, delay=0.5):
    for _ in range(attempts):  # the kickstarted app takes a moment to bind
        if port_up(port):
            return True
        time.sleep(delay)
    return False


def ensure_up(sop_dir, label=None, port=None):
    """No-op when the dashboard answers; otherwise start it and confirm. Returns (ok, msg).

    port is normally baked into the cron entry at install time (cron's env lacks
    SMBOS_DASHBOARD_PORT); falls back to resolving from sop_dir/triggers.json if not passed."""
    label = label or legacy.AGENT_LABEL
    if port is None:
        port = lib.dashboard_port(sop_dir)
    if port_up(port):
        return True, "up on {}".format(port)
    gui = "gui/{}/{}".format(os.getuid(), label)
    subprocess.run(["launchctl", "kickstart", "-k", gui], capture_output=True)
    if _wait_up(port):
        return True, "kickstarted; up on {}".format(port)
    # agent not loaded (e.g. just after boot, before login bootstrap): register it, then start
    subprocess.run(["launchctl", "bootstrap", "gui/{}".format(os.getuid()),
                    str(legacy.plist_path())], capture_output=True)
    subprocess.run(["launchctl", "kickstart", "-k", gui], capture_output=True)
    ok = _wait_up(port)
    return ok, ("recovered on {}".format(port) if ok else "still down on {}".format(port))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sop-dir", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)
    sop_dir = lib.resolve_sop_dir(explicit=args.sop_dir)
    ok, msg = ensure_up(sop_dir, port=args.port)
    print(msg, flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
