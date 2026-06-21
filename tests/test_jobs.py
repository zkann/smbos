"""Tests for jobs.py (the recurring-jobs manager). Pure compile/reconcile/validate over strings +
tmp jobs.d dirs; the real crontab is never touched (sync's IO is the only un-unit-tested seam)."""
import json
import os

import jobs
import pytest


def _spec(tmp, name, **kw):
    d = tmp / "jobs.d"
    d.mkdir(exist_ok=True)
    (d / (name + ".json")).write_text(json.dumps({"name": name, **kw}), encoding="utf-8")


def test_compile_job_is_a_tagged_line():
    units = [{"name": "broker-audit", "kind": "job", "schedule": "30 8 * * *",
              "command": "/usr/bin/python3 /x/audit.py >/dev/null 2>&1"}]
    assert jobs.compile_cron(units, 501) == [
        "30 8 * * * /usr/bin/python3 /x/audit.py >/dev/null 2>&1  # smbos-unit:broker-audit"]


def test_compile_keychain_job_kickstarts_the_agent():
    units = [{"name": "mail-fetch", "kind": "keychain-job", "schedule": "0 * * * *"}]
    assert jobs.compile_cron(units, 501) == [
        "0 * * * * /bin/launchctl kickstart -k gui/501/com.smbos.mail-fetch >/dev/null 2>&1"
        "  # smbos-unit:mail-fetch"]


def test_compile_skips_disabled_and_escapes_percent():
    units = [{"name": "off", "kind": "job", "schedule": "@daily", "command": "x", "enabled": False},
             {"name": "pct", "kind": "job", "schedule": "@daily", "command": "date +%Y"}]
    # disabled skipped; cron's % escaped so it doesn't become a newline
    assert jobs.compile_cron(units, 501) == [r"@daily date +\%Y  # smbos-unit:pct"]


def test_reconcile_claims_only_what_a_unit_replaces():
    existing = [
        "0 9 * * * /other/thing  # not ours",        # foreign -> keep
        "0 * * * * /legacy/mail  # smbos-mail-old",   # a unit CLAIMS this tag -> strip
        "*/5 * * * * /digest  # smbos-digest",        # smbos, but NOT claimed (owned elsewhere) -> KEEP
        "0 8 * * * /stale  # smbos-unit:gone",        # a removed unit's own line -> strip
    ]
    desired = ["0 * * * * /new/mail  # smbos-unit:mail-fetch"]
    out = jobs.reconcile(existing, desired, claimed_tags=["# smbos-mail-old"])
    # claimed legacy + own-unit lines stripped; the foreign AND the non-claimed smbos-digest line kept
    assert out == [
        "0 9 * * * /other/thing  # not ours",
        "*/5 * * * * /digest  # smbos-digest",
        "0 * * * * /new/mail  # smbos-unit:mail-fetch",
    ]


def test_reconcile_empty_crontab_just_adds():
    assert jobs.reconcile([], ["@daily x  # smbos-unit:a"]) == ["@daily x  # smbos-unit:a"]


def test_load_units_local_overrides_public(tmp_path, monkeypatch):
    pub = tmp_path / "pub" / "jobs.d"
    pub.mkdir(parents=True)
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: pub)
    (pub / "a.json").write_text(json.dumps({"name": "a", "kind": "job", "schedule": "@daily", "command": "PUBLIC"}))
    _spec(tmp_path, "a", kind="job", schedule="@daily", command="LOCAL")   # local override of public 'a'
    _spec(tmp_path, "b", kind="keychain-job", schedule="0 * * * *")
    by = {u["name"]: u for u in jobs.load_units(tmp_path)}
    assert by["a"]["command"] == "LOCAL" and by["b"]["kind"] == "keychain-job"


def test_validate_rejects_injection_and_bad_specs(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")  # no public dir
    for bad in (
        {"name": "bad name", "kind": "job", "schedule": "@daily", "command": "x"},        # space in name
        {"name": "svc", "kind": "service", "schedule": "@daily"},                          # services excluded
        {"name": "nlsched", "kind": "job", "schedule": "@daily\n0 0 * * * evil", "command": "x"},  # newline
        {"name": "cr", "kind": "job", "schedule": "@daily", "command": "x\rmalicious"},     # CR fragments
        {"name": "vt", "kind": "job", "schedule": "@daily", "command": "x\x0bevil"},        # vertical tab too
        {"name": "nocmd", "kind": "job", "schedule": "@daily"},                            # job without command
        {"name": "hashsched", "kind": "job", "schedule": "@daily # smbos-unit:x", "command": "x"},  # # in schedule
        {"name": "extra", "kind": "job", "schedule": "* * * * * /tmp/evil", "command": "x"},  # 6 fields -> inject cmd
        {"name": "few", "kind": "job", "schedule": "* * *", "command": "x"},               # too few fields
        {"name": "bogus", "kind": "job", "schedule": "@bogus", "command": "x"},            # not a real @shortcut
        {"name": "numcmd", "kind": "job", "schedule": "@daily", "command": 5},             # non-string command
        {"name": "listcmd", "kind": "job", "schedule": "@daily", "command": ["x"]},        # non-string command
        {"name": "bareclaim", "kind": "job", "schedule": "@daily", "command": "x", "claims": "#"},     # bare #
        {"name": "wordsclaim", "kind": "job", "schedule": "@daily", "command": "x", "claims": "# a b"}, # multi-word
        {"name": "txtclaim", "kind": "job", "schedule": "@daily", "command": "x", "claims": "nope"},   # not a tag
    ):
        d = tmp_path / "jobs.d"
        d.mkdir(exist_ok=True)
        (d / "bad.json").write_text(json.dumps(bad))
        with pytest.raises(jobs.JobSpecError):
            jobs.load_units(tmp_path)


def test_validate_accepts_5_fields_and_shortcuts(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")
    _spec(tmp_path, "a", kind="job", schedule="*/5 8 * * 1-5", command="x")   # 5 fields with a step + range
    _spec(tmp_path, "b", kind="keychain-job", schedule="@hourly")
    assert {u["name"] for u in jobs.load_units(tmp_path)} == {"a", "b"}


def test_reconcile_keeps_a_foreign_line_mentioning_the_tag():
    # ownership is the TRAILING tag; a foreign line whose command merely mentions it must survive
    existing = ['*/10 * * * * grep "# smbos-unit:" /var/log/x  # my monitor']
    assert jobs.reconcile(existing, [], []) == existing


def test_sop_dir_uses_canonical_resolver_not_argv(monkeypatch):
    import smbos_lib
    monkeypatch.setattr(smbos_lib, "resolve_sop_dir", lambda **k: "/SENTINEL")
    assert str(jobs._sop_dir()) == "/SENTINEL"   # via lib.resolve_sop_dir (argv-free), not legacy's wrapper


def test_sync_status_detects_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")   # local specs only
    _spec(tmp_path, "a", kind="job", schedule="30 8 * * *", command="run-a")
    _spec(tmp_path, "b", kind="job", schedule="0 9 * * *", command="run-b")
    synced = jobs.compile_cron(jobs.load_units(tmp_path), os.getuid())       # what a clean sync would write

    monkeypatch.setattr(jobs.legacy, "_read_crontab", lambda: "# foreign\n" + "\n".join(synced) + "\n")
    assert jobs.sync_status(tmp_path) == {"a": True, "b": True}              # both live -> synced

    monkeypatch.setattr(jobs.legacy, "_read_crontab", lambda: synced[0] + "\n")
    assert jobs.sync_status(tmp_path) == {"a": True, "b": False}             # b missing -> pending

    stale_a = synced[0].replace("30 8", "45 7")                             # a's live line is the OLD schedule
    monkeypatch.setattr(jobs.legacy, "_read_crontab", lambda: stale_a + "\n" + synced[1] + "\n")
    assert jobs.sync_status(tmp_path) == {"a": False, "b": True}             # a edited but not synced -> pending

    # an empty/unreadable crontab -> UNKNOWN for every unit, never a false "all pending" (the FDA-less
    # broker gets "" from `crontab -l`; treating that as all-pending would cry wolf on every healthy frame)
    monkeypatch.setattr(jobs.legacy, "_read_crontab", lambda: "")
    assert jobs.sync_status(tmp_path) == {"a": None, "b": None}

    # an ORPHANED tag (a deleted job's line still in cron, no spec) is flagged pending, not ignored
    orphan = "0 0 * * * run-x  # smbos-unit:deleted-job"
    monkeypatch.setattr(jobs.legacy, "_read_crontab", lambda: "\n".join(synced) + "\n" + orphan + "\n")
    assert jobs.sync_status(tmp_path) == {"a": True, "b": True, "deleted-job": False}


def test_sync_status_disabled_and_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")
    _spec(tmp_path, "a", kind="job", schedule="30 8 * * *", command="run-a", enabled=False)
    line = "30 8 * * * run-a  # smbos-unit:a"
    monkeypatch.setattr(jobs.legacy, "_read_crontab", lambda: line + "\n")
    assert jobs.sync_status(tmp_path) == {"a": False}                        # disabled but still in cron -> pending removal
    monkeypatch.setattr(jobs.legacy, "_read_crontab", lambda: "# unrelated\n")  # non-empty, no line for a
    assert jobs.sync_status(tmp_path) == {"a": True}                         # disabled + correctly absent -> synced
    monkeypatch.setattr(jobs.legacy, "_read_crontab", lambda: None)
    assert jobs.sync_status(tmp_path) == {"a": None}                         # crontab unavailable -> unknown


def test_set_job_fields_edits_and_persists(tmp_path):
    _spec(tmp_path, "j", kind="job", schedule="0 9 * * *", command="run-j", description="old")
    out = jobs.set_job_fields(tmp_path, "j", {"schedule": "30 8 * * *", "description": "new", "enabled": False})
    assert out["schedule"] == "30 8 * * *" and out["description"] == "new" and out["enabled"] is False
    on_disk = json.loads((tmp_path / "jobs.d" / "j.json").read_text())
    assert on_disk["schedule"] == "30 8 * * *"          # persisted
    assert on_disk["command"] == "run-j"                # untouched fields preserved


def test_set_job_fields_rejects_bad_input(tmp_path):
    _spec(tmp_path, "j", kind="job", schedule="0 9 * * *", command="run-j")
    for fields in ({"command": "evil"},                 # not an editable field
                   {"schedule": "30 25 * * *"},         # hour out of range
                   {"schedule": "boom"},                # not 5 fields
                   {"description": 5},                  # non-string
                   {"enabled": "yes"}):                 # non-bool
        with pytest.raises(jobs.JobSpecError):
            jobs.set_job_fields(tmp_path, "j", fields)
    with pytest.raises(jobs.JobSpecError):
        jobs.set_job_fields(tmp_path, "absent", {"schedule": "0 9 * * *"})       # no such local spec
    with pytest.raises(jobs.JobSpecError):
        jobs.set_job_fields(tmp_path, "../evil", {"schedule": "0 9 * * *"})      # bad name (no path traversal)
    assert json.loads((tmp_path / "jobs.d" / "j.json").read_text())["schedule"] == "0 9 * * *"   # unchanged


def test_set_job_fields_description_only_skips_schedule_validation(tmp_path):
    # a named-day schedule: _validate accepts it (5 fields), the numeric range-check would reject it.
    # a description-only edit must NOT re-validate the unchanged schedule (else the job is uneditable).
    _spec(tmp_path, "j", kind="job", schedule="0 9 * * MON-FRI", command="run-j")
    out = jobs.set_job_fields(tmp_path, "j", {"description": "weekday mornings"})
    assert out["description"] == "weekday mornings" and out["schedule"] == "0 9 * * MON-FRI"


def test_schedule_in_range():
    for s in ("30 8 * * *", "0 */2 * * *", "0 9 * * 1-5", "15,45 3 * * *", "@daily", "0 0 1 1 0"):
        assert jobs._schedule_in_range(s), s
    for s in ("30 25 * * *", "0 9 99 * *", "0 9 * * 9", "*/0 * * * *", "boom", "1 2 3 4"):
        assert not jobs._schedule_in_range(s), s


def test_create_job_writes_a_valid_spec(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")
    spec = jobs.create_job(tmp_path, {"name": "newjob", "kind": "job", "schedule": "30 8 * * *",
                                      "command": "run-it", "description": "a thing"})
    assert spec["name"] == "newjob" and spec["enabled"] is True
    on_disk = json.loads((tmp_path / "jobs.d" / "newjob.json").read_text())
    assert on_disk["command"] == "run-it" and on_disk["schedule"] == "30 8 * * *"
    kj = jobs.create_job(tmp_path, {"name": "kjob", "kind": "keychain-job", "schedule": "@hourly"})
    assert kj["kind"] == "keychain-job"          # a keychain-job needs no command


def test_create_job_rejects_bad_input(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")
    _spec(tmp_path, "taken", kind="job", schedule="0 9 * * *", command="x")
    for fields in ({"name": "taken", "kind": "job", "schedule": "0 9 * * *", "command": "x"},      # duplicate
                   {"name": "../evil", "kind": "job", "schedule": "0 9 * * *", "command": "x"},     # bad name
                   {"name": "nocmd", "kind": "job", "schedule": "0 9 * * *"},                       # job needs a command
                   {"name": "badsched", "kind": "job", "schedule": "0 25 * * *", "command": "x"},   # out of range
                   {"name": "badkind", "kind": "weird", "schedule": "0 9 * * *", "command": "x"},   # bad kind
                   {"name": "sneaky", "kind": "job", "schedule": "0 9 * * *", "command": "x", "claims": "# y"},   # unknown field
                   {"name": "trail\n", "kind": "job", "schedule": "0 9 * * *", "command": "x"}):                 # trailing newline in name
        with pytest.raises(jobs.JobSpecError):
            jobs.create_job(tmp_path, fields)
    assert not (tmp_path / "jobs.d" / "badsched.json").exists()   # a rejected create writes nothing


def test_delete_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_plugin_jobs_d", lambda: tmp_path / "nope")
    _spec(tmp_path, "doomed", kind="job", schedule="0 9 * * *", command="x")
    jobs.delete_job(tmp_path, "doomed")
    assert not (tmp_path / "jobs.d" / "doomed.json").exists()
    with pytest.raises(jobs.JobSpecError):
        jobs.delete_job(tmp_path, "doomed")          # already gone
    with pytest.raises(jobs.JobSpecError):
        jobs.delete_job(tmp_path, "../evil")         # bad name (no traversal)
