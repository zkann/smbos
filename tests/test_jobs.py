"""Tests for jobs.py (the recurring-jobs manager). Pure compile/reconcile/validate over strings +
tmp jobs.d dirs; the real crontab is never touched (sync's IO is the only un-unit-tested seam)."""
import json

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
        {"name": "bad name", "kind": "job", "schedule": "@daily", "command": "x"},     # space in name
        {"name": "svc", "kind": "service", "schedule": "@daily"},                       # services excluded
        {"name": "inj", "kind": "job", "schedule": "@daily\n0 0 * * * evil", "command": "x"},  # newline inject
        {"name": "nocmd", "kind": "job", "schedule": "@daily"},                         # job without command
        {"name": "cmdnl", "kind": "job", "schedule": "@daily", "command": "x\nrm -rf /"},  # newline in command
        {"name": "tag", "kind": "job", "schedule": "@daily # smbos-unit:x", "command": "x"},  # # in schedule
        {"name": "ec", "kind": "job", "schedule": "@daily", "command": "x", "claims": ""},  # empty claims (would strip all)
        {"name": "nc", "kind": "job", "schedule": "@daily", "command": "x", "claims": "no-hash"},  # claims not a tag
    ):
        d = tmp_path / "jobs.d"
        d.mkdir(exist_ok=True)
        (d / "bad.json").write_text(json.dumps(bad))
        with pytest.raises(jobs.JobSpecError):
            jobs.load_units(tmp_path)
