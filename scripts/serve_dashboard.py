#!/usr/bin/env python3
"""Serve the SmbOS dashboard in live mode.

Usage: serve_dashboard.py [sop_dir]

GET  /?t=<token>    the dashboard, regenerated from disk on every load
POST /api/suggest   {"path": "...", "text": "..."} with X-Token header;
                    appends the suggestion to that SOP's
                    "Notes for next revision" section

Suggestions are append-only and tagged "via dashboard"; restructuring an SOP
stays with Claude's propose/approve flow. Binds 127.0.0.1 only, random port,
per-run token. Stdlib only, no network beyond localhost. Ctrl-C to stop.
"""
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_dashboard import SKIP_NAMES, build_html, resolve_sop_dir
from smbos_lib import find_sop as lib_find_sop
from smbos_lib import (frontmatter_field, is_drifted, parse_frontmatter,
                       run_lock_held, split_frontmatter)

TOKEN = secrets.token_urlsafe(16)
MAX_TEXT = 2000
NOTES_HEADING = "## Notes for next revision"
# Where the dashboard was launched from; a queued task inherits this as its target
# project, so the right Claude Code session picks it up. Home dir means run-anywhere.
LAUNCH_CWD = str(Path.cwd())


def append_suggestion(sop_dir, rel_path, text):
    root = sop_dir.resolve()
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise PermissionError("path escapes the SOP directory")
    if target.suffix != ".md" or target.name in SKIP_NAMES or not target.is_file():
        raise FileNotFoundError("not an SOP file")

    bullet = "- ({}, via dashboard) {}".format(date.today().isoformat(), " ".join(text.split()))
    content = target.read_text(encoding="utf-8")
    if NOTES_HEADING in content:
        head, _, tail = content.partition(NOTES_HEADING)
        nxt = tail.find("\n## ")
        if nxt == -1:
            content = head + NOTES_HEADING + tail.rstrip() + "\n" + bullet + "\n"
        else:
            section, rest = tail[:nxt], tail[nxt:]
            content = head + NOTES_HEADING + section.rstrip() + "\n" + bullet + "\n" + rest
    else:
        block = "\n" + NOTES_HEADING + "\n\n" + bullet + "\n"
        cl = content.find("\n## Changelog")
        if cl == -1:
            content = content.rstrip() + "\n" + block
        else:
            content = content[:cl] + block + content[cl:]
    target.write_text(content, encoding="utf-8")


def resolve_pending_file(sop_dir, rel_name, decision):
    p = sop_dir / "pending" / Path(str(rel_name)).name
    if not p.is_file():
        raise FileNotFoundError("no such pending item")
    if decision not in ("approve", "discard"):
        raise ValueError("decision must be approve or discard")
    text = p.read_text(encoding="utf-8")
    new_status = "approved" if decision == "approve" else "discarded"
    text = re.sub(r"^status: *pending$", f"status: {new_status}", text, count=1, flags=re.M)
    p.write_text(text + f"\n> {new_status} via dashboard on "
                 f"{datetime.now(timezone.utc).isoformat()}\n", encoding="utf-8")
    return new_status


def required_inputs(sop_dir, sid):
    for p in sop_dir.rglob(f"{sid}.md"):
        m = re.search(r"^run_inputs: *(.+)$", p.read_text(encoding="utf-8")[:900], re.M)
        return m.group(1).strip() if m else None
    return None


def sop_declared_folder(sop_dir, sid):
    """An SOP's canonical `folder:` (expanded), or None. When set, queued tasks
    and launches for that SOP route there regardless of where the dashboard was
    launched, e.g. a client SOP always runs in its project folder."""
    match = next(iter(sop_dir.rglob(f"{sid}.md")), None) if sid else None
    if match is None:
        return None
    raw = parse_frontmatter(match.read_text(encoding="utf-8")).get("folder")
    if not raw:
        return None
    folder = Path(os.path.expanduser(os.path.expandvars(raw.strip()))).resolve()
    return str(folder) if folder.is_dir() else None


def queue_run(sop_dir, sop_id, inputs=None, scope="here"):
    sid = re.sub(r"[^a-z0-9-]", "", str(sop_id).lower())
    if not sid or not any(sop_dir.rglob(f"{sid}.md")):
        raise ValueError("unknown task")
    qdir = sop_dir / "queue"
    qdir.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    declared = sop_declared_folder(sop_dir, sid)
    if scope == "anywhere":
        project = ""  # owner explicitly chose any folder
    elif declared:
        project = declared  # the SOP knows its home (e.g. a client SOP -> its project folder)
    elif LAUNCH_CWD in (str(Path.home()), str(sop_dir)):
        project = ""
    else:
        project = LAUNCH_CWD
    body = (f"---\nsop: {sid}\nrequested: {now.isoformat()}\nsource: dashboard\n"
            f"project: {project}\nstatus: queued\n---\n")
    if inputs:
        body += f"\nOwner's notes for the run:\n{str(inputs)[:2000]}\n"
    (qdir / f"{now.strftime('%Y%m%dT%H%M%S')}-{sid}.md").write_text(body, encoding="utf-8")
    return sid, project


def has_unrecorded_changes(sop_dir, sid):
    for p in sop_dir.rglob(f"{sid}.md"):
        meta, body = split_frontmatter(p.read_text(encoding="utf-8"))
        return is_drifted(meta, body)
    return False


def start_run(sop_dir, sop_id, inputs=None, prepare=False):
    sid = re.sub(r"[^a-z0-9-]", "", str(sop_id).lower())
    if not sid:
        raise ValueError("bad sop id")
    if run_lock_held(sop_dir, sid):
        raise ValueError("This procedure is already running. Its result will appear "
                         'under "waiting for you" when it finishes.')
    if has_unrecorded_changes(sop_dir, sid):
        raise ValueError("This procedure was changed outside the normal save flow. "
                         "Review the changes with Claude first; saving them restores running.")
    needed = required_inputs(sop_dir, sid)
    if needed and not inputs:
        raise ValueError(f"This task needs information before it can run: {needed}. "
                         "Fill in the box above the Run button.")
    runner = Path(__file__).resolve().parent / "run_sop.py"
    cmd = [sys.executable, str(runner), sid, "--source", "dashboard", "--sop-dir", str(sop_dir)]
    if prepare:
        cmd.append("--prepare")
    if inputs:
        cmd += ["--inputs", str(inputs)[:2000]]
    log = (sop_dir / "trigger.log").open("a")
    subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
    return sid


def applescript_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


# The terminal app the dashboard was launched from; used as the default for
# launches so Claude opens in the terminal the owner actually uses.
TERM_PROGRAM = os.environ.get("TERM_PROGRAM", "")

TERMINAL_SCRIPTS = {
    "terminal": 'tell application "Terminal"\nactivate\ndo script "{cmd}"\nend tell',
    "iterm": ('tell application "iTerm"\nactivate\n'
              'set newWindow to (create window with default profile)\n'
              'tell current session of newWindow\nwrite text "{cmd}"\nend tell\nend tell'),
}


def preferred_terminal(sop_dir):
    """Config override in triggers.json ("terminal"), else detect from the
    environment the dashboard inherited, else Terminal.app."""
    cfg = sop_dir / "triggers.json"
    if cfg.exists():
        try:
            val = str(json.loads(cfg.read_text(encoding="utf-8")).get("terminal") or "").lower()
            if val in TERMINAL_SCRIPTS:
                return val
        except ValueError:
            pass
    if TERM_PROGRAM == "iTerm.app":
        return "iterm"
    return "terminal"


# Permission posture for the Claude session a launch button opens. The owner
# clicked to run their own documented SOP, so these only affect sessions they
# explicitly start from the dashboard.
#   "trust" (default): accept file edits without asking, still ask before
#                      running commands, and remember the launch folder so the
#                      workspace trust dialog stops re-appearing on every launch.
#   "ask":             no flags; Claude prompts the normal way.
#   "skip":            bypass every check (zero prompts).
LAUNCH_PERMISSION_FLAGS = {
    "ask": [],
    "trust": ["--permission-mode", "acceptEdits"],
    "skip": ["--dangerously-skip-permissions"],
}
DEFAULT_LAUNCH_PERMISSION = "trust"
# The store Claude Code writes when you accept the workspace trust dialog.
CLAUDE_CONFIG = str(Path.home() / ".claude.json")


def launch_permission(sop_dir):
    """Config override in triggers.json ("launch_permission"); default 'trust'."""
    cfg = sop_dir / "triggers.json"
    if cfg.exists():
        try:
            raw = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                val = str(raw.get("launch_permission") or "").lower()
                if val in LAUNCH_PERMISSION_FLAGS:
                    return val
        except (OSError, ValueError):
            pass
    return DEFAULT_LAUNCH_PERMISSION


def save_triggers(sop_dir, mutate):
    """Read-modify-write triggers.json atomically, preserving its file mode
    (it can hold the digest Slack webhook). `mutate(data)` edits the dict."""
    cfg = sop_dir / "triggers.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    mutate(data)
    mode = cfg.stat().st_mode if cfg.exists() else None
    tmp = cfg.with_name(cfg.name + ".smbos-tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, cfg)


def set_launch_permission(sop_dir, value):
    value = str(value).lower()
    if value not in LAUNCH_PERMISSION_FLAGS:
        raise ValueError("posture must be one of: " + ", ".join(LAUNCH_PERMISSION_FLAGS))
    save_triggers(sop_dir, lambda d: d.__setitem__("launch_permission", value))
    return value


def set_budget(sop_dir, amount):
    try:
        amt = round(float(amount), 2)
    except (TypeError, ValueError):
        raise ValueError("budget must be a number")
    if amt < 0:
        raise ValueError("budget cannot be negative")
    save_triggers(sop_dir, lambda d: d.__setitem__("monthly_budget_usd", amt))
    return amt


def set_terminal(sop_dir, value):
    value = str(value).lower()
    if value not in TERMINAL_SCRIPTS:
        raise ValueError("terminal must be one of: " + ", ".join(TERMINAL_SCRIPTS))
    save_triggers(sop_dir, lambda d: d.__setitem__("terminal", value))
    return value


def set_digest_notify(sop_dir, on):
    on = bool(on)
    def m(d):
        dg = d.get("digest")
        d["digest"] = ({**dg} if isinstance(dg, dict) else {})
        d["digest"]["notify"] = on
    save_triggers(sop_dir, m)
    return on


# ---- digest schedule via a tagged crontab line (best-effort, idempotent) ----
DIGEST_CRON_TAG = "# smbos-digest"


def _read_crontab():
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return None  # crontab unavailable


def _write_crontab(text):
    try:
        r = subprocess.run(["crontab", "-"], input=text, text=True,
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def digest_schedule(sop_dir):
    """Current digest time from the tagged crontab line, or None."""
    cur = _read_crontab()
    if not cur:
        return None
    for line in cur.splitlines():
        if DIGEST_CRON_TAG in line:
            parts = line.split()
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return {"hour": int(parts[1]), "minute": int(parts[0])}
    return None


def _crontab_without_digest(cur):
    return "\n".join(l for l in cur.splitlines() if DIGEST_CRON_TAG not in l)


def set_digest_schedule(sop_dir, hour, minute):
    """Install/replace the daily digest cron line. Returns True on success."""
    hour, minute = int(hour), int(minute)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("bad time")
    cur = _read_crontab()
    if cur is None:
        return False
    runner = Path(__file__).resolve().parent / "digest.py"
    rq = shlex.quote(str(runner))
    sq = shlex.quote(str(sop_dir))
    logq = shlex.quote(str(Path(sop_dir) / "trigger.log"))
    line = (f"{minute} {hour} * * * /usr/bin/env python3 {rq} "
            f"--sop-dir {sq} >> {logq} 2>&1  {DIGEST_CRON_TAG}")
    body = _crontab_without_digest(cur).rstrip("\n")
    new = (body + "\n" if body else "") + line + "\n"
    return _write_crontab(new)


def clear_digest_schedule(sop_dir):
    cur = _read_crontab()
    if cur is None:
        return False
    return _write_crontab(_crontab_without_digest(cur).rstrip("\n") + "\n")


def remember_folder_trust(folder):
    """Persist workspace trust for `folder`, the same record the trust dialog
    writes when you click "trust". Skips home and the filesystem root (too broad
    to auto-trust) and a folder already trusted, and never raises: on any problem
    the launch still happens and Claude just asks once, as before."""
    folder = Path(folder).expanduser().resolve()
    if folder == Path.home().resolve() or folder == folder.parent:
        return
    cfg = Path(CLAUDE_CONFIG)
    try:
        mode = cfg.stat().st_mode
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    projects = data.get("projects")
    if projects is None:
        projects = data["projects"] = {}
    elif not isinstance(projects, dict):
        return
    key = str(folder)
    entry = projects.get(key)
    if isinstance(entry, dict) and entry.get("hasTrustDialogAccepted") is True:
        return
    projects[key] = {**(entry if isinstance(entry, dict) else {}),
                     "hasTrustDialogAccepted": True}
    tmp = cfg.with_name(cfg.name + ".smbos-tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.chmod(tmp, mode)  # the temp file is created with umask; restore the
        os.replace(tmp, cfg)  # original mode so a 0600 private config stays private
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def open_terminal_with_claude(folder, prompt, terminal="terminal",
                              permission=DEFAULT_LAUNCH_PERMISSION):
    """Open a terminal window in `folder` running claude with `prompt` (macOS).

    `permission` picks the launched session's posture (see LAUNCH_PERMISSION_FLAGS);
    "trust" also remembers `folder` so the workspace trust dialog stops nagging."""
    if sys.platform != "darwin":
        raise ValueError("launching Claude from the dashboard only works on macOS")
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise ValueError("that folder no longer exists")
    if permission == "trust":
        remember_folder_trust(folder)
    flags = LAUNCH_PERMISSION_FLAGS.get(permission, [])
    claude_cmd = " ".join(["claude", *flags, shlex.quote(prompt)])
    shell_cmd = "cd " + shlex.quote(str(folder)) + " && " + claude_cmd
    script = TERMINAL_SCRIPTS.get(terminal, TERMINAL_SCRIPTS["terminal"]).format(
        cmd=applescript_escape(shell_cmd))
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=20)


def launch(sop_dir, payload):
    """Map a validated launch request to a Terminal+Claude window.

    The browser only sends identifiers; folders and prompts are derived
    server-side from the owner's own files, never from request strings.
    """
    kind = str(payload.get("kind") or "")
    home = str(Path.home())
    if kind == "queue":
        p = sop_dir / "queue" / Path(str(payload.get("file") or "")).name
        if not p.is_file():
            raise ValueError("no such queued task")
        meta = parse_frontmatter(p.read_text(encoding="utf-8"))
        folder = meta.get("project") or home
        prompt = "I'm ready to do the task on my plate: " + (meta.get("sop") or "")
    elif kind == "sop":
        sid = re.sub(r"[^a-z0-9-]", "", str(payload.get("id") or "").lower())
        match = next(iter(sop_dir.rglob(f"{sid}.md")), None) if sid else None
        if match is None:
            raise ValueError("unknown task")
        meta = parse_frontmatter(match.read_text(encoding="utf-8"))
        trigger = (meta.get("triggers") or "").split(",")[0].strip()
        folder = (sop_declared_folder(sop_dir, sid)
                  or (LAUNCH_CWD if LAUNCH_CWD not in (home, str(sop_dir)) else home))
        prompt = trigger or ("Let's do: " + (meta.get("title") or sid))
    elif kind == "approved":
        folder = LAUNCH_CWD if LAUNCH_CWD not in (home, str(sop_dir)) else home
        prompt = "Execute my approved pending actions."
    elif kind == "open_file":
        sid = re.sub(r"[^a-z0-9-]", "", str(payload.get("id") or "").lower())
        match = next(iter(sop_dir.rglob(f"{sid}.md")), None) if sid else None
        if match is None:
            raise ValueError("unknown task")
        subprocess.run(["open", str(match)], check=True, timeout=15)
        return "opened file"
    elif kind == "reveal":
        subprocess.run(["open", str(sop_dir)], check=True, timeout=15)
        return "opened folder"
    else:
        raise ValueError("unknown launch kind")
    open_terminal_with_claude(folder, prompt, terminal=preferred_terminal(sop_dir),
                              permission=launch_permission(sop_dir))
    return "launched"


class Handler(BaseHTTPRequestHandler):
    sop_dir = None

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/ping":
            ok = (self.headers.get("X-Token") == TOKEN
                  or parse_qs(u.query).get("t", [""])[0] == TOKEN)
            return self._send(200 if ok else 403, '{"ok": true}' if ok else '{"error":"bad token"}')
        if u.path not in ("/", "/index.html"):
            return self._send(404, '{"error":"not found"}')
        if parse_qs(u.query).get("t", [""])[0] != TOKEN:
            return self._send(403, '{"error":"bad or missing token"}')
        proj = "" if LAUNCH_CWD in (str(Path.home()), str(self.sop_dir)) else Path(LAUNCH_CWD).name
        sched = digest_schedule(self.sop_dir)
        tj, dg, budget = {}, {}, 0.0
        try:
            tj = json.loads((self.sop_dir / "triggers.json").read_text(encoding="utf-8"))
            if isinstance(tj, dict):
                dg = tj.get("digest") if isinstance(tj.get("digest"), dict) else {}
                budget = float(tj.get("monthly_budget_usd") or 0)
        except (OSError, ValueError, TypeError):
            pass
        html = build_html(self.sop_dir, {
            "live": True, "token": TOKEN, "project": proj,
            "launch_permission": launch_permission(self.sop_dir),
            "terminal": preferred_terminal(self.sop_dir),
            "budget": budget,
            "digest_notify": bool(dg.get("notify", True)),
            "digest_time": ("%02d:%02d" % (sched["hour"], sched["minute"])) if sched else "",
        })
        return self._send(200, html, "text/html")

    def do_POST(self):
        if self.path not in ("/api/suggest", "/api/resolve", "/api/run", "/api/queue", "/api/launch", "/api/launch-permission", "/api/settings"):
            return self._send(404, '{"error":"not found"}')
        if self.headers.get("X-Token") != TOKEN:
            return self._send(403, '{"error":"bad or missing token"}')
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 65536)
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/suggest":
                text = str(payload.get("text", "")).strip()[:MAX_TEXT]
                if not text:
                    return self._send(400, '{"error":"empty suggestion"}')
                append_suggestion(self.sop_dir, str(payload.get("path", "")), text)
                return self._send(200, '{"ok":true}')
            if self.path == "/api/resolve":
                pending_name = Path(str(payload.get("file", ""))).name
                status = resolve_pending_file(self.sop_dir, pending_name,
                                              str(payload.get("decision", "")))
                reason = str(payload.get("reason") or "").strip()[:MAX_TEXT]
                if status == "discarded" and reason:
                    sop_id = frontmatter_field(self.sop_dir / "pending" / pending_name, "sop")
                    target = lib_find_sop(self.sop_dir, sop_id) if sop_id else None
                    if target:
                        append_suggestion(self.sop_dir, str(target.relative_to(self.sop_dir)),
                                          f"(discarded a prepared result) {reason}")
                return self._send(200, json.dumps({"ok": True, "status": status}))
            if self.path == "/api/launch":
                msg = launch(self.sop_dir, payload)
                return self._send(200, json.dumps({"ok": True, "did": msg}))
            if self.path == "/api/launch-permission":
                try:
                    val = set_launch_permission(self.sop_dir, payload.get("value", ""))
                except ValueError as e:
                    return self._send(400, json.dumps({"error": str(e)}))
                return self._send(200, json.dumps({"ok": True, "launch_permission": val}))
            if self.path == "/api/settings":
                key = str(payload.get("key") or "")
                val = payload.get("value")
                try:
                    if key == "budget":
                        return self._send(200, json.dumps({"ok": True, "budget": set_budget(self.sop_dir, val)}))
                    if key == "terminal":
                        return self._send(200, json.dumps({"ok": True, "terminal": set_terminal(self.sop_dir, val)}))
                    if key == "digest_notify":
                        return self._send(200, json.dumps({"ok": True, "digest_notify": set_digest_notify(self.sop_dir, val)}))
                    if key == "digest_time":
                        if not val:
                            ok = clear_digest_schedule(self.sop_dir)
                            return self._send(200, json.dumps({"ok": ok, "digest_time": ""}))
                        hh, mm = (int(x) for x in str(val).split(":", 1))
                        ok = set_digest_schedule(self.sop_dir, hh, mm)
                        if not ok:
                            return self._send(200, json.dumps({"ok": False,
                                "error": "Could not update your schedule (no crontab access on this machine)."}))
                        return self._send(200, json.dumps({"ok": True, "digest_time": "%02d:%02d" % (hh, mm)}))
                except (ValueError, TypeError) as e:
                    return self._send(400, json.dumps({"error": str(e)}))
                return self._send(400, json.dumps({"error": "unknown setting"}))
            if self.path == "/api/queue":
                sid, project = queue_run(self.sop_dir, payload.get("id", ""),
                                         inputs=str(payload.get("inputs") or "").strip() or None,
                                         scope=str(payload.get("scope") or "here"))
                dest = Path(project).name if project else "any folder"
                return self._send(200, json.dumps({"ok": True, "queued": sid, "dest": dest}))
            if self.path == "/api/run":
                mode = payload.get("mode")
                if mode not in (None, "", "prepare"):
                    raise ValueError("unknown run mode")
                if mode == "prepare":
                    sid = start_run(self.sop_dir, payload.get("id", ""),
                                    inputs=str(payload.get("inputs") or "").strip() or None,
                                    prepare=True)
                    return self._send(200, json.dumps({"ok": True, "id": sid, "mode": "prepare"}))
                sid = start_run(self.sop_dir, payload.get("id", ""),
                                inputs=str(payload.get("inputs") or "").strip() or None)
                return self._send(200, json.dumps({"ok": True, "started": sid}))
        except (PermissionError, FileNotFoundError, ValueError) as e:
            return self._send(400, json.dumps({"error": str(e)}))
        except json.JSONDecodeError:
            return self._send(400, '{"error":"invalid JSON"}')
        except Exception:
            return self._send(500, '{"error":"server error"}')


def main():
    sop_dir = resolve_sop_dir()
    Handler.sop_dir = sop_dir
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    print("SmbOS live dashboard: http://127.0.0.1:{}/?t={}".format(port, TOKEN), flush=True)
    print("Reading {}. Saved suggestions land in each SOP's notes. Ctrl-C to stop.".format(sop_dir), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
