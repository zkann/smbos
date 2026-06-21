"""Tests for system_status -- the dashboard's System-view aggregator. Pure aggregation over a tmp
jobs.d + tmp liveness files + a tmp state.db; never touches the real ~/sops."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import system_status as st          # noqa: E402
import jobs                         # noqa: E402
import state_store as ss            # noqa: E402


def _spec(sop_dir, name, **fields):
    d = sop_dir / "jobs.d"
    d.mkdir(exist_ok=True)
    spec = {"name": name, "kind": "job", "schedule": "@daily", "command": "x", **fields}
    (d / (name + ".json")).write_text(json.dumps(spec))


def test_newest_mtime(tmp_path):
    assert st._newest_mtime(str(tmp_path / "none-*.txt")) is None
    a = tmp_path / "a.txt"
    a.write_text("1")
    os.utime(a, (time.time() - 100, time.time() - 100))     # backdate a
    b = tmp_path / "b.txt"
    b.write_text("2")                                       # b is newer
    assert st._newest_mtime(str(tmp_path / "*.txt")) == b.stat().st_mtime


def test_job_health_ok_stale_unknown(tmp_path):
    now_ts = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc).timestamp()
    f = tmp_path / "beat"
    f.write_text("x")
    os.utime(f, (now_ts - 30 * 60, now_ts - 30 * 60))       # 30 min old, threshold 90 -> ok
    ok = st.job_health({"name": "j", "kind": "job", "liveness_file": str(f), "max_age_minutes": 90}, now_ts)
    assert ok["health"] == "ok" and ok["age_min"] == 30 and ok["last_run"] is not None
    os.utime(f, (now_ts - 200 * 60, now_ts - 200 * 60))     # 200 min old (> 90, <= 270) -> stale
    assert st.job_health({"name": "j", "kind": "job", "liveness_file": str(f), "max_age_minutes": 90},
                         now_ts)["health"] == "stale"
    os.utime(f, (now_ts - 400 * 60, now_ts - 400 * 60))     # 400 min (> 3x90) -> down (dead, not just late)
    assert st.job_health({"name": "j", "kind": "job", "liveness_file": str(f), "max_age_minutes": 90},
                         now_ts)["health"] == "down"
    # an explicit max_age_minutes=0 is respected (not swallowed by `or` into the default)
    os.utime(f, (now_ts - 30 * 60, now_ts - 30 * 60))
    assert st.job_health({"name": "j", "kind": "job", "liveness_file": str(f), "max_age_minutes": 0},
                         now_ts)["health"] != "ok"
    # declared a liveness_file that doesn't exist -> never ran -> stale
    assert st.job_health({"name": "j", "kind": "job", "liveness_file": str(tmp_path / "nope")},
                         now_ts)["health"] == "stale"
    # no liveness_file declared -> unknown (can't judge)
    j = st.job_health({"name": "j", "kind": "job"}, now_ts)
    assert j["health"] == "unknown" and j["age_min"] is None


def test_system_status_overall_is_worst_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")   # only the local specs
    monkeypatch.setattr(jobs, "sync_status", lambda d: {})                   # hermetic: don't read the real crontab
    now = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    fresh = tmp_path / "fresh"
    fresh.write_text("x")
    os.utime(fresh, (now.timestamp() - 10 * 60, now.timestamp() - 10 * 60))
    _spec(tmp_path, "a-healthy", liveness_file=str(fresh), max_age_minutes=90)
    _spec(tmp_path, "z-stale", liveness_file=str(tmp_path / "missing"), max_age_minutes=90)
    out = st.system_status(tmp_path, now=now)
    assert out["health"] == "stale"                          # worst of {ok, stale}
    assert {j["name"]: j["health"] for j in out["jobs"]} == {"a-healthy": "ok", "z-stale": "stale"}
    assert out["jobs"][0]["name"] == "a-healthy"             # sorted by name


def test_system_status_pipeline_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")
    monkeypatch.setattr(jobs, "sync_status", lambda d: {})
    ss.record_task(tmp_path, "inbox", "reply", "a", source_ref="t1")        # inits the store; 1 waiting
    ss.record_route(tmp_path, "email", "x1", "job")                         # 1 job route
    out = st.system_status(tmp_path, now=datetime(2026, 6, 20, tzinfo=timezone.utc))
    assert out["pipeline"]["waiting_tasks"] == 1
    assert out["pipeline"]["routes"].get("job.routed") == 1
    assert out["pipeline"]["eval_feedback"] == 0


def test_system_status_surfaces_sync_state(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")
    _spec(tmp_path, "a-applied")
    _spec(tmp_path, "b-pending")
    monkeypatch.setattr(jobs, "sync_status", lambda d: {"a-applied": True, "b-pending": False})
    out = st.system_status(tmp_path, now=datetime(2026, 6, 20, tzinfo=timezone.utc))
    assert {j["name"]: j["synced"] for j in out["jobs"]} == {"a-applied": True, "b-pending": False}
    assert out["pending_sync"] == 1                          # one shown job isn't live in cron yet


def test_pending_sync_counts_disabled_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")
    _spec(tmp_path, "shown")                                 # enabled + synced
    # sync_status reports a DISABLED unit still in cron (not among the shown enabled rows) as pending
    monkeypatch.setattr(jobs, "sync_status", lambda d: {"shown": True, "off-but-in-cron": False})
    out = st.system_status(tmp_path, now=datetime(2026, 6, 20, tzinfo=timezone.utc))
    assert [j["name"] for j in out["jobs"]] == ["shown"]     # the disabled unit isn't shown
    assert out["pending_sync"] == 1                          # but its drift is counted -> the banner still fires


def test_describe_cron():
    # common shapes -> plain English
    assert st.describe_cron("30 8 * * *") == "every day at 8:30 AM"
    assert st.describe_cron("15 3 * * *") == "every day at 3:15 AM"
    assert st.describe_cron("30 14 * * *") == "every day at 2:30 PM"
    assert st.describe_cron("0 0 * * *") == "every day at 12:00 AM"
    assert st.describe_cron("0 * * * *") == "every hour"
    assert st.describe_cron("5 * * * *") == "every hour at :05"
    assert st.describe_cron("0 0 * * 0") == "every Sunday at 12:00 AM"
    assert st.describe_cron("@daily") == "every day at midnight"
    # a list / range / step is too complex -> fall back to the raw expression (never wrong, just terse)
    assert st.describe_cron("*/5 * * * *") == "*/5 * * * *"
    assert st.describe_cron("0 9 * * 1-5") == "0 9 * * 1-5"
    assert st.describe_cron("") == ""
    # out-of-range fields fall back to the raw expression, never a wrong gloss (hour 25 -> "1:30 PM")
    assert st.describe_cron("30 25 * * *") == "30 25 * * *"
    assert st.describe_cron("99 8 * * *") == "99 8 * * *"
    assert st.describe_cron("0 24 * * *") == "0 24 * * *"
    assert st.describe_cron("30 8 * * 9") == "30 8 * * 9"
    assert st.describe_cron("99 * * * *") == "99 * * * *"


def test_job_dict_carries_schedule_human_and_description(tmp_path):
    j = st.job_health({"name": "j", "kind": "job", "schedule": "30 8 * * *", "description": "sorts the inbox"},
                      datetime(2026, 6, 20, tzinfo=timezone.utc).timestamp())
    assert j["schedule_human"] == "every day at 8:30 AM"
    assert j["description"] == "sorts the inbox"
    # a spec with no description -> the field is present but None (the row just omits the subline)
    assert st.job_health({"name": "j", "kind": "job"}, 0)["description"] is None
    # a non-string description (malformed / future user-edited spec) is coerced to None, never streamed
    # (React renders j.description as a child and throws on an object) -> render safety
    assert st.job_health({"name": "j", "kind": "job", "description": {"oops": 1}}, 0)["description"] is None
    assert st.job_health({"name": "j", "kind": "job", "description": ["a", "b"]}, 0)["description"] is None
