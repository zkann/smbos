"""Tests for miss_log -- the found-miss capture log. scripts/ is on sys.path via conftest; writes go
to tmp_path so the real miss log is never touched."""
import miss_log as ml


def test_log_miss_defaults_and_roundtrip(tmp_path):
    p = tmp_path / "misses.jsonl"
    rec = ml.log_miss("duplicate task created for an already-sent invoice", path=p, ref="invoice-42")
    assert rec["caught_by"] == "human" and rec["status"] == "open"
    assert rec["ts"].endswith("+00:00")
    got = ml.read_misses(p)
    assert len(got) == 1 and got[0]["ref"] == "invoice-42"


def test_unknown_keys_dropped(tmp_path):
    p = tmp_path / "m.jsonl"
    ml.log_miss("x", path=p, layer="guard", bogus="nope", taxonomy="duplicate-task")
    rec = ml.read_misses(p)[0]
    assert rec["layer"] == "guard" and rec["taxonomy"] == "duplicate-task"
    assert "bogus" not in rec


def test_read_skips_malformed_and_non_dict(tmp_path):
    p = tmp_path / "m.jsonl"
    # unparseable garbage, blank lines, AND valid-JSON-but-not-a-record scalars/arrays
    p.write_text('{"title": "ok"}\nnot json\n42\n[1, 2]\n\n{"title": "ok2"}\n', encoding="utf-8")
    got = ml.read_misses(p)
    assert [m["title"] for m in got] == ["ok", "ok2"]  # scalars/arrays excluded, garbage skipped
    ml.report(got)  # must not raise on the filtered set


def test_log_miss_recovers_from_missing_trailing_newline(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text('{"title": "first"}', encoding="utf-8")  # a prior write cut off before its newline
    ml.log_miss("second", path=p)
    assert [m["title"] for m in ml.read_misses(p)] == ["first", "second"]  # both stay readable


def test_report_frequency_first_and_excludes_fixed(tmp_path):
    p = tmp_path / "m.jsonl"
    ml.log_miss("a", path=p, taxonomy="duplicate-task")
    ml.log_miss("b", path=p, taxonomy="duplicate-task")
    ml.log_miss("c", path=p, taxonomy="wrong-due-date")
    ml.log_miss("d", path=p, taxonomy="duplicate-task", status="fixed")
    out = ml.report(ml.read_misses(p))
    assert "3 open / 4 total" in out  # the fixed one is excluded from the open count
    buckets = [line for line in out.splitlines() if line.strip().endswith(("duplicate-task", "wrong-due-date"))]
    assert buckets[0].strip().startswith("2")  # the recurring bucket (count 2) ranks first
