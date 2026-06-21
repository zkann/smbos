"""system_status.py -- one read of "is SmbOS healthy and what's flowing", for the dashboard's System
view and a `status` CLI.

Pure aggregation over state already on disk, no new plumbing:
  - the job registry (jobs.d, via jobs.load_units),
  - each job's last successful run = the newest file matching the `liveness_file` its OWN spec declares
    (a job rewrites/creates that file only on success, so its mtime is the heartbeat),
  - the pipeline counts from the typed store (routed_item lanes, the eval feedback, the waiting plate).

Generic by construction: a job's health comes from its own spec's `liveness_file`, so no private path is
baked in here. The private specs (in <sop_dir>/jobs.d) declare their own files; this just reads them.

    jobs.d --load_units--> [units] --(newest mtime of each unit.liveness_file)--> per-job last-run/health
    state.db ----------------------------------------> pipeline counts
                                       worst job health = overall health
"""
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs                          # the registry: load_units + _sop_dir
import state_store as ss             # the typed store (routing store + plate)

# fallback staleness threshold when a spec doesn't declare max_age_minutes: hourly-ish vs daily-ish
DEFAULT_MAX_AGE_MIN = {"keychain-job": 90, "job": 1560}
_RANK = {"ok": 0, "unknown": 1, "stale": 2, "down": 3}   # worst-wins ordering for overall health


def _newest_mtime(pattern):
    """Newest mtime (epoch seconds) among files matching `pattern` (a path or glob, ~ expanded), or None
    if nothing matches. `getmtime` is wrapped per file: a match can vanish between the glob and the stat,
    which a separate `os.path.exists()` check wouldn't close (still TOCTOU-racy)."""
    times = []
    for m in glob.glob(os.path.expanduser(str(pattern))):
        try:
            times.append(os.path.getmtime(m))
        except OSError:              # vanished between glob and stat, or unreadable
            continue
    return max(times) if times else None


_DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
_CRON_SHORTCUTS = {
    "@hourly": "every hour", "@daily": "every day at midnight", "@midnight": "every day at midnight",
    "@weekly": "every Sunday at midnight", "@monthly": "the 1st of each month at midnight",
    "@yearly": "every Jan 1 at midnight", "@annually": "every Jan 1 at midnight", "@reboot": "at startup",
}


def _fmt_clock(hh, mm):
    """24h -> a 12h clock string: (8, 30) -> '8:30 AM', (0, 0) -> '12:00 AM', (14, 0) -> '2:00 PM'."""
    return "{}:{:02d} {}".format(hh % 12 or 12, mm, "AM" if hh < 12 else "PM")


def _in_range(field, hi):
    """True iff `field` is a plain integer in [0, hi]. An out-of-range value (hour 25, minute 99,
    dow 9) must fall back to the raw expression, not a wrong gloss like '1:30 PM' or '8:99 AM'."""
    return field.isdigit() and 0 <= int(field) <= hi


def describe_cron(expr):
    """Plain-English gloss of a cron schedule for a hover tooltip: '30 8 * * *' -> 'every day at 8:30 AM'.
    Covers the common shapes (named shortcuts, every-minute/hour, daily/weekly at a fixed time); anything
    with a list, range, or step falls back to the raw expression, so the tooltip is never wrong, just
    terse."""
    s = (expr or "").strip()
    if not s:
        return ""
    if s in _CRON_SHORTCUTS:
        return _CRON_SHORTCUTS[s]
    f = s.split()
    if len(f) != 5 or any(c in s for c in ",-/"):    # not a plain 5-field cron, or a list/range/step
        return s
    minute, hour, dom, mon, dow = f
    if minute == "*" and hour == "*":
        return "every minute"
    if hour == "*" and _in_range(minute, 59):
        return "every hour" if int(minute) == 0 else "every hour at :{:02d}".format(int(minute))
    if _in_range(minute, 59) and _in_range(hour, 23):
        clock = _fmt_clock(int(hour), int(minute))
        if dom == "*" and mon == "*" and dow == "*":
            return "every day at {}".format(clock)
        if dom == "*" and mon == "*" and _in_range(dow, 7):
            return "every {} at {}".format(_DOW[int(dow) % 7], clock)
    return s


def job_health(unit, now_ts):
    """A registered job's last-run + health from its declared `liveness_file`. health is
    ok | stale | unknown (no liveness_file declared) -- never crashes on a missing file."""
    lf = unit.get("liveness_file")
    last = _newest_mtime(lf) if lf else None
    age_min = None if last is None else int((now_ts - last) / 60)
    max_age = unit.get("max_age_minutes")
    if max_age is None:                          # respect an explicit 0 (don't let `or` swallow it)
        max_age = DEFAULT_MAX_AGE_MIN.get(unit.get("kind"), 1560)
    if not lf:
        health = "unknown"                       # no heartbeat declared -> can't judge
    elif last is None:
        health = "stale"                         # declared a file that was never written -> never ran
    elif age_min <= max_age:
        health = "ok"
    elif age_min <= max_age * 3:
        health = "stale"                         # missed a run or two
    else:
        health = "down"                          # dead for 3x its interval -> not just late
    return {"name": unit.get("name"), "schedule": unit.get("schedule"), "kind": unit.get("kind"),
            "schedule_human": describe_cron(unit.get("schedule")),
            "last_run": datetime.fromtimestamp(last, timezone.utc).isoformat() if last else None,
            "age_min": age_min, "health": health}


def _pipeline(sop_dir):
    """Generic flow counts from the typed store. Returns empties (not an error) if the store is absent,
    and NEVER creates it: a read-only status check (running every 30s) must not write a 0-byte state.db
    on a fresh install."""
    db = Path(ss.db_path(sop_dir)).resolve()     # absolute, so as_uri() below can't raise on a relative path
    if not db.is_file():
        return {"routes": {}, "eval_feedback": None, "waiting_tasks": None}
    try:
        con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)   # read-only: never write during a status read
        try:
            routes = {"{}.{}".format(lane, status): n for lane, status, n in
                      con.execute("SELECT lane,status,count(*) FROM routed_item GROUP BY lane,status")}
            feedback = con.execute("SELECT count(*) FROM feedback").fetchone()[0]
            waiting = con.execute("SELECT count(*) FROM task WHERE status='waiting'").fetchone()[0]
        finally:
            con.close()
        return {"routes": routes, "eval_feedback": feedback, "waiting_tasks": waiting}
    except sqlite3.Error:
        return {"routes": {}, "eval_feedback": None, "waiting_tasks": None}


def system_status(sop_dir, now=None):
    """The whole picture: overall health (worst job), per-job last-run/health, pipeline counts."""
    now = now or datetime.now(timezone.utc)
    now_ts = now.timestamp()
    units = [u for u in jobs.load_units(sop_dir) if u.get("enabled", True)]
    job_rows = sorted((job_health(u, now_ts) for u in units), key=lambda j: j["name"] or "")
    worst = max((j["health"] for j in job_rows), key=lambda h: _RANK.get(h, 1), default="ok")
    return {"checked_at": now.isoformat(), "health": worst, "jobs": job_rows, "pipeline": _pipeline(sop_dir)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    st = system_status(jobs._sop_dir())
    if "--json" in argv:
        print(json.dumps(st))
        return 0
    print("SmbOS status  {}  health: {}".format(st["checked_at"][:16], st["health"].upper()))
    for j in st["jobs"]:
        age = "{}m ago".format(j["age_min"]) if j["age_min"] is not None else "no run on record"
        print("  {:14} {:12} {:18} {}".format(j["name"] or "?", j["schedule"] or "", age, j["health"]))
    p = st["pipeline"]
    routes = " ".join("{} {}".format(k, v) for k, v in sorted(p["routes"].items())) or "none"
    print("  flow: routes {} | eval {} | waiting {}".format(routes, p["eval_feedback"], p["waiting_tasks"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
