"""Tests for the idempotent work-state importer. Stdlib + pytest; generic example data."""
import json
import sqlite3

import pytest

import importer
import state_store as ss


def _subjects(sop_dir):
    return sorted(t["subject"] for t in ss.plate(sop_dir))


def test_import_records_basic(tmp_path):
    recs = [
        {"id": "inv-1", "subject": "Acme invoice", "priority": 3},
        {"id": "inv-2", "subject": "Globex invoice", "priority": 1},
    ]
    result = importer.import_records(tmp_path, "invoicing", recs)
    assert result["imported"] == 2 and result["errors"] == []
    assert _subjects(tmp_path) == ["Acme invoice", "Globex invoice"]


def test_import_is_idempotent(tmp_path):
    recs = [{"id": "inv-1", "subject": "Acme invoice"}]
    importer.import_records(tmp_path, "invoicing", recs)
    importer.import_records(tmp_path, "invoicing", recs)  # re-run
    assert len(ss.plate(tmp_path)) == 1  # upsert, no duplicate


def test_reimport_updates_and_is_resumable(tmp_path):
    # simulate an interrupted run: first 2 records land, then a re-run of the full set
    full = [
        {"id": "inv-1", "subject": "Acme invoice", "priority": 1},
        {"id": "inv-2", "subject": "Globex invoice", "priority": 1},
        {"id": "inv-3", "subject": "Initech invoice", "priority": 1},
    ]
    importer.import_records(tmp_path, "invoicing", full[:2])  # partial
    # the re-run updates inv-1's subject and adds inv-3, no dupes
    full[0] = {"id": "inv-1", "subject": "Acme invoice (revised)", "priority": 5}
    importer.import_records(tmp_path, "invoicing", full)
    rows = ss.plate(tmp_path)
    assert len(rows) == 3
    revised = next(r for r in rows if r["source_ref"] == "inv-1")
    assert revised["subject"] == "Acme invoice (revised)" and revised["priority"] == 5


def test_import_skips_bad_records_but_keeps_good(tmp_path):
    recs = [
        {"id": "ok-1", "subject": "valid"},
        {"id": "bad-1"},                       # missing subject
        "not-an-object",                        # not a dict
        {"id": "bad-2", "subject": "x", "priority": "high"},  # non-int priority
        {"id": "ok-2", "subject": "also valid"},
    ]
    result = importer.import_records(tmp_path, "ops", recs)
    assert result["imported"] == 2
    assert len(result["errors"]) == 3
    assert _subjects(tmp_path) == ["also valid", "valid"]


def test_import_jsonl_roundtrip_and_bad_line(tmp_path):
    src = tmp_path / "items.jsonl"
    src.write_text(
        json.dumps({"id": "a", "subject": "onboarding Acme", "priority": 2}) + "\n"
        + "{not valid json}\n"
        + "\n"  # blank line ignored
        + json.dumps({"id": "b", "subject": "onboarding Globex"}) + "\n",
        encoding="utf-8",
    )
    result = importer.import_jsonl(tmp_path, "onboarding", src)
    assert result["imported"] == 2
    assert len(result["errors"]) == 1 and "bad JSON" in result["errors"][0]
    assert _subjects(tmp_path) == ["onboarding Acme", "onboarding Globex"]


def test_import_jsonl_idempotent_across_reruns(tmp_path):
    src = tmp_path / "items.jsonl"
    src.write_text(json.dumps({"id": "a", "subject": "x"}) + "\n", encoding="utf-8")
    importer.import_jsonl(tmp_path, "ops", src)
    importer.import_jsonl(tmp_path, "ops", src)
    assert len(ss.plate(tmp_path)) == 1


def test_custom_source_key(tmp_path):
    recs = [{"ticket": "T-100", "subject": "ticket work"}]
    importer.import_records(tmp_path, "support", recs, source_key="ticket")
    importer.import_records(tmp_path, "support", recs, source_key="ticket")  # idempotent on T-100
    rows = ss.plate(tmp_path)
    assert len(rows) == 1 and rows[0]["source_ref"] == "T-100"


def test_records_without_source_ref_are_not_deduped(tmp_path):
    recs = [{"subject": "no id here"}]
    importer.import_records(tmp_path, "ops", recs)
    importer.import_records(tmp_path, "ops", recs)
    assert len(ss.plate(tmp_path)) == 2  # NULL source_ref always inserts


def test_priority_null_defaults_to_zero(tmp_path):
    # explicit JSON null must NOT drop the row (it defaults to 0)
    r = importer.import_records(tmp_path, "ops", [{"id": "a", "subject": "x", "priority": None}])
    assert r["imported"] == 1 and r["errors"] == []
    assert ss.plate(tmp_path)[0]["priority"] == 0


def test_priority_bool_is_rejected(tmp_path):
    r = importer.import_records(tmp_path, "ops", [{"id": "a", "subject": "x", "priority": True}])
    assert r["imported"] == 0 and len(r["errors"]) == 1


def test_whitespace_only_subject_is_skipped(tmp_path):
    r = importer.import_records(tmp_path, "ops", [{"id": "a", "subject": "   "}])
    assert r["imported"] == 0 and len(r["errors"]) == 1


def test_empty_source_via_importer_not_deduped(tmp_path):
    recs = [{"id": "", "subject": "one"}, {"id": "", "subject": "two"}]
    importer.import_records(tmp_path, "ops", recs)
    assert len(ss.plate(tmp_path)) == 2  # empty source -> NULL -> not deduped


def test_store_error_is_collected_not_raised(tmp_path, monkeypatch):
    # a transient sqlite error mid-batch must be collected, not escape uncaught (resumable)
    calls = {"n": 0}
    real = ss.upsert_task

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("database is locked")
        return real(*a, **k)

    monkeypatch.setattr(importer.ss, "upsert_task", flaky)
    recs = [{"id": "1", "subject": "a"}, {"id": "2", "subject": "b"}, {"id": "3", "subject": "c"}]
    result = importer.import_records(tmp_path, "ops", recs)  # must not raise
    assert result["imported"] == 2 and len(result["errors"]) == 1


def test_cli_missing_file_is_clean(tmp_path, capsys):
    rc = importer.main(["--sop-dir", str(tmp_path), "--domain", "ops",
                        "--jsonl", str(tmp_path / "nope.jsonl")])
    assert rc == 1
    assert "could not read" in capsys.readouterr().err  # clean message, not a traceback


def test_cli_exit_zero_with_per_record_skips(tmp_path):
    src = tmp_path / "items.jsonl"
    src.write_text('{"id":"a","subject":"good"}\n{"id":"b"}\n', encoding="utf-8")  # 2nd missing subject
    rc = importer.main(["--sop-dir", str(tmp_path), "--domain", "ops", "--jsonl", str(src)])
    assert rc == 0  # imported>0 with expected skips is success, not failure
