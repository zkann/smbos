import json
import subprocess
import sys

from conftest import SCRIPTS


def rpc(library, messages):
    inp = "\n".join(json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "mcp_server.py"), str(library)],
                          input=inp, capture_output=True, text=True, timeout=30)
    return [json.loads(line) for line in proc.stdout.splitlines()]


def call(name, args, mid=10):
    return {"jsonrpc": "2.0", "id": mid, "method": "tools/call",
            "params": {"name": name, "arguments": args}}


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"}}


def text_of(resp):
    return resp["result"]["content"][0]["text"]


def test_handshake_and_tools(library):
    out = rpc(library, [INIT, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    assert out[0]["result"]["serverInfo"]["name"] == "smbos"
    assert "SmbOS" in out[0]["result"]["instructions"]
    names = [t["name"] for t in out[1]["result"]["tools"]]
    assert {"list_sops", "read_sop", "suggest_change", "create_draft_sop",
            "pending_runs", "resolve_pending", "automation_costs"} <= set(names)


def test_list_and_read(library):
    out = rpc(library, [INIT, call("list_sops", {}, 2),
                        call("read_sop", {"id": "weekly-metrics-report"}, 3)])
    assert "Weekly metrics report" in text_of(out[1])
    assert "## My way" in text_of(out[2])


def test_create_draft_and_suggest(library):
    out = rpc(library, [INIT,
                        call("create_draft_sop", {"id": "thank-you", "title": "Thanks",
                                                  "category": "clients",
                                                  "content": "## Steps\n1. Say thanks.\n"}, 2),
                        call("suggest_change", {"id": "weekly-metrics-report",
                                                "suggestion": "Lead with cash"}, 3)])
    assert "clients/thank-you.md" in text_of(out[1])
    assert (library / "clients" / "thank-you.md").exists()
    assert "status: draft" in (library / "clients" / "thank-you.md").read_text()
    assert "via chat) Lead with cash" in (library / "ops" / "weekly-metrics-report.md").read_text()


def test_resolve_pending_traversal_guard(library):
    pend = library / "pending"
    pend.mkdir()
    (pend / "x.md").write_text("---\nsop: a\nstatus: pending\n---\n")
    out = rpc(library, [INIT,
                        call("resolve_pending", {"file": "../../etc/passwd", "decision": "approve"}, 2),
                        call("resolve_pending", {"file": "x.md", "decision": "approve"}, 3)])
    assert "No pending file" in text_of(out[1])
    assert "NOT happened yet" in text_of(out[2])
    assert "status: approved" in (pend / "x.md").read_text()


def test_costs_humanized(library):
    (library / "triggers.json").write_text(json.dumps(
        {"monthly_budget_usd": 20.0,
         "triggers": [{"id": "t", "sop": "weekly-metrics-report",
                       "spec": "cron(57 8 * * 1)", "kind": "cron", "enabled": True}]}))
    out = rpc(library, [INIT, call("automation_costs", {}, 2)])
    assert "every Monday at 8:57 AM" in text_of(out[1])
    assert "cron(" not in text_of(out[1])


def test_list_sops_flags_unrecorded_changes(library):
    from smbos_lib import content_fingerprint, set_frontmatter_fields, split_frontmatter
    sop = library / "ops" / "weekly-metrics-report.md"
    text = sop.read_text()
    _m, body = split_frontmatter(text)
    sop.write_text(set_frontmatter_fields(text, {"content_hash": content_fingerprint(body, _m)}))
    sop.write_text(sop.read_text().replace("Do the thing.", "Changed."))
    out = rpc(library, [INIT, call("list_sops", {})])
    txt = text_of(out[-1])
    assert "UNRECORDED CHANGES" in txt
    assert "v1" in txt
