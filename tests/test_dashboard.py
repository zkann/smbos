import json
import re

import generate_dashboard as gd


def extra_of(html):
    m = re.search(r'<script id="extra"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def cfg_of(html):
    m = re.search(r'<script id="cfg"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_build_html_static(library):
    html = gd.build_html(library)
    assert cfg_of(html)["live"] is False
    data = extra_of(html)
    assert data["pending"] == [] and data["work"] == []


def test_humanized_schedules_no_raw_cron(library):
    (library / "triggers.json").write_text(json.dumps(
        {"monthly_budget_usd": 20.0,
         "triggers": [
             {"id": "a", "sop": "weekly-metrics-report", "spec": "cron(57 8 * * 1)",
              "kind": "cron", "enabled": True},
             {"id": "b", "sop": "weekly-metrics-report", "spec": "cron(0 9 * * *)",
              "kind": "cron", "enabled": False}]}))
    data = extra_of(gd.build_html(library))
    assert data["schedules"] == {"weekly-metrics-report": ["every Monday at 8:57 AM"]}
    assert "cron(" not in json.dumps(data["schedules"])


def test_pending_and_failures_translated(library):
    from datetime import datetime, timezone
    pend = library / "pending"
    pend.mkdir()
    (pend / "x.md").write_text(
        "---\nsop: weekly-metrics-report\ntrigger_source: linear\ncreated: c\nstatus: pending\n---\n")
    (library / "runs.jsonl").write_text(json.dumps(
        {"ts": datetime.now(timezone.utc).isoformat(), "sop": "a", "result": "error",
         "cost_usd": 0, "note": "timeout after 900s"}) + "\n")
    data = extra_of(gd.build_html(library))
    assert data["pending"][0]["source_plain"] == "a Linear event"
    assert data["failures"][0]["plain"] == "the run took too long and was stopped"


def test_work_items_surface(library):
    w = library / "work"
    w.mkdir()
    (w / "a.md").write_text(
        "---\nid: a\ntitle: Ship it\nstages: plan,build\nstage: build\nstatus: active\nproject: /x/skypulse\n---\n")
    (w / "b.md").write_text("---\nid: b\ntitle: Done thing\nstage: x\nstatus: done\n---\n")
    items = extra_of(gd.build_html(library))["work"]
    assert len(items) == 1
    assert items[0]["title"] == "Ship it" and items[0]["project"] == "skypulse"


def test_runtime_dirs_not_collected_as_sops(library):
    for d in ["pending", "queue", "work", "payloads"]:
        sub = library / d
        sub.mkdir(exist_ok=True)
        (sub / "x.md").write_text("---\nid: ghost\n---\n")
    paths = [f["path"] for f in gd.collect(library)]
    assert paths == ["ops/weekly-metrics-report.md"]


def test_queued_surfaces(library):
    q = library / "queue"
    q.mkdir()
    (q / "a.md").write_text(
        "---\nsop: send-invoice\nproject: /x/skypulse\nstatus: queued\n---\n")
    (q / "b.md").write_text("---\nsop: other\nproject: \nstatus: done\n---\n")
    data = extra_of(gd.build_html(library))
    assert data["queued"] == [{"sop": "send-invoice", "file": "a.md", "project": "skypulse"}]
