#!/usr/bin/env python3
"""SmbOS MCP server: the SOP library over the Model Context Protocol (stdio).

Exposes the same files the Claude Code plugin manages, so SOPs work from
Claude Desktop, claude.ai, and mobile. Stdlib only; newline-delimited
JSON-RPC 2.0 on stdin/stdout per the MCP stdio transport.

Usage: mcp_server.py [sop_dir]   (else $SOP_DIR, else ~/sops)
"""
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

SKIP_NAMES = {"INDEX.md", "_template.md"}
NON_SOP_DIRS = {"pending", "payloads", "triggers", "archive", "queue", "work"}
NOTES_HEADING = "## Notes for next revision"
MAX_TEXT = 4000

INSTRUCTIONS = """SmbOS manages this user's Standard Operating Procedures: their documented way of
doing recurring business tasks. The rules:

1. Before helping with a business task, call list_sops and check for a match. If one
   matches, call read_sop and FOLLOW IT, especially the "My way" section, which
   overrides your defaults even when your default seems better.
2. An SOP with status "draft" is unverified; confirm details with the user as you go.
3. You cannot edit SOPs directly from here. When the user corrects how something
   should be done, call suggest_change so the correction lands in the SOP's notes;
   their next Claude Code session folds it in with approval.
4. When the user describes a NEW recurring task and how they do it, offer to save it:
   call create_draft_sop with a complete SOP body.
5. pending_runs lists automated runs parked at an approval gate. Show the user the
   prepared work; resolve_pending records their approve/discard decision. Approved
   actions are executed by their next Claude Code session, not from here; say so.
6. automation_costs answers "what has automation cost" with real numbers.
Speak plainly: say "runs every Monday at 8:57 AM", never "cron(57 8 * * 1)"."""


def sop_dir():
    for c in [sys.argv[1] if len(sys.argv) > 1 else None, os.environ.get("SOP_DIR"),
              str(Path.home() / "sops")]:
        if c and Path(c).expanduser().is_dir():
            return Path(c).expanduser()
    sys.exit("smbos-mcp: no SOP directory found")


D = sop_dir()


def iter_sops():
    for p in sorted(D.rglob("*.md")):
        rel = p.relative_to(D)
        if p.name in SKIP_NAMES or p.name.startswith(".") or any(x in NON_SOP_DIRS for x in rel.parts):
            continue
        yield p


def frontmatter(text):
    meta = {}
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith("#"):
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    return meta


def find_sop(sop_id):
    for p in iter_sops():
        if p.stem == sop_id or frontmatter(p.read_text(encoding="utf-8")[:800]).get("id") == sop_id:
            return p
    return None


def humanize_cron(spec):
    m = re.match(r"cron\((\S+) (\S+) (\S+) (\S+) (\S+)\)", spec)
    if not m:
        return spec
    minute, hour, dom, _, dow = m.groups()
    days = {"0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
            "4": "Thursday", "5": "Friday", "6": "Saturday", "*": None}
    try:
        t = f"{int(hour) % 12 or 12}:{int(minute):02d} {'AM' if int(hour) < 12 else 'PM'}"
    except ValueError:
        return spec
    day = days.get(dow, dow)
    if day:
        return f"every {day} at {t}"
    if dom != "*":
        return f"monthly on day {dom} at {t}"
    return f"every day at {t}"


# ---- tool implementations ----

def t_list_sops(args):
    rows = []
    for p in iter_sops():
        meta = frontmatter(p.read_text(encoding="utf-8")[:900])
        rows.append(f"- {meta.get('title', p.stem)} (id: {meta.get('id', p.stem)}) "
                    f"[{meta.get('status', 'draft')}] runs={meta.get('runs', '0')} "
                    f"last_used={meta.get('last_used', 'never')} | triggers: {meta.get('triggers', '')}")
    return "The user's SOP library:\n" + "\n".join(rows) if rows else "No SOPs yet."


def t_read_sop(args):
    p = find_sop(args["id"])
    return p.read_text(encoding="utf-8") if p else f"No SOP with id '{args['id']}'."


def t_suggest_change(args):
    p = find_sop(args["id"])
    if not p:
        return f"No SOP with id '{args['id']}'."
    text = " ".join(str(args["suggestion"]).split())[:MAX_TEXT]
    bullet = f"- ({date.today().isoformat()}, via chat) {text}"
    content = p.read_text(encoding="utf-8")
    if NOTES_HEADING in content:
        head, _, tail = content.partition(NOTES_HEADING)
        nxt = tail.find("\n## ")
        if nxt == -1:
            content = head + NOTES_HEADING + tail.rstrip() + "\n" + bullet + "\n"
        else:
            content = head + NOTES_HEADING + tail[:nxt].rstrip() + "\n" + bullet + "\n" + tail[nxt:]
    else:
        content = content.rstrip() + "\n\n" + NOTES_HEADING + "\n\n" + bullet + "\n"
    p.write_text(content, encoding="utf-8")
    return ("Saved to the SOP's notes. The user's next Claude Code session will offer to fold "
            "it into the SOP properly.")


def t_create_draft_sop(args):
    sid = re.sub(r"[^a-z0-9-]", "", str(args["id"]).lower().replace(" ", "-"))[:60]
    cat = re.sub(r"[^a-z0-9-]", "", str(args["category"]).lower())[:30] or "ops"
    if not sid:
        return "Invalid id."
    if find_sop(sid):
        return f"An SOP with id '{sid}' already exists; use suggest_change instead."
    body = str(args["content"])
    if not body.startswith("---"):
        today = date.today().isoformat()
        body = (f"---\nid: {sid}\ntitle: {args.get('title', sid)}\ncategory: {cat}\n"
                f"triggers: {args.get('trigger_phrases', '')}\nversion: 1\ncreated: {today}\n"
                f"updated: {today}\nlast_used: never\nruns: 0\nclean_runs: 0\nstatus: draft\n"
                f"source: captured via chat\n---\n\n" + body)
    target = D / cat / f"{sid}.md"
    target.parent.mkdir(exist_ok=True)
    target.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
    idx = D / "INDEX.md"
    if idx.exists():
        with idx.open("a", encoding="utf-8") as f:
            f.write(f"- **{args.get('title', sid)}** ({cat}/{sid}.md): captured via chat, draft "
                    f"| triggers: {args.get('trigger_phrases', '')}\n")
    return (f"Draft SOP saved as {cat}/{sid}.md. It starts as a draft; the first time it runs "
            "for real it gets verified and promoted.")


def t_pending_runs(args):
    pdir = D / "pending"
    items = []
    if pdir.is_dir():
        for p in sorted(pdir.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            meta = frontmatter(text)
            if meta.get("status", "pending") != "pending":
                continue
            body = re.sub(r"^---.*?---\s*", "", text, flags=re.S)
            items.append(f"### {p.name}\nSOP: {meta.get('sop')} | started by: {meta.get('trigger_source')} "
                         f"| {meta.get('created')}\n\n{body.strip()}")
    if not items:
        return "Nothing is waiting for approval."
    return (f"{len(items)} automated run(s) are parked, waiting for the user's decision. Show each "
            "and ask approve or discard, then call resolve_pending.\n\n" + "\n\n---\n\n".join(items))


def t_resolve_pending(args):
    name = Path(str(args["file"])).name
    p = D / "pending" / name
    if not p.is_file():
        return f"No pending file named '{name}'."
    decision = str(args["decision"]).lower()
    if decision not in ("approve", "discard"):
        return "decision must be 'approve' or 'discard'."
    text = p.read_text(encoding="utf-8")
    new_status = "approved" if decision == "approve" else "discarded"
    text = re.sub(r"^status: *pending$", f"status: {new_status}", text, count=1, flags=re.M)
    stamp = f"\n> {new_status} via chat on {datetime.now(timezone.utc).isoformat()}"
    if args.get("note"):
        stamp += f": {str(args['note'])[:500]}"
    p.write_text(text + stamp + "\n", encoding="utf-8")
    if decision == "approve":
        return ("Marked approved. IMPORTANT: the action has NOT happened yet; the user's next "
                "Claude Code session will execute it. Tell the user that.")
    return "Discarded. Nothing will be sent or done."


def t_automation_costs(args):
    cap = 0.0
    cfg = D / "triggers.json"
    triggers = []
    if cfg.exists():
        try:
            reg = json.loads(cfg.read_text(encoding="utf-8"))
            cap = float(reg.get("monthly_budget_usd") or 0)
            triggers = reg.get("triggers", [])
        except (ValueError, TypeError):
            pass
    lines = []
    for t in triggers:
        sched = humanize_cron(t["spec"]) if t["kind"] == "cron" else f"when {t['spec']} happens"
        lines.append(f"- {t['sop']}: {sched} ({'on' if t.get('enabled') else 'off'})")
    total, runs, by_sop = 0.0, 0, {}
    log = D / "runs.jsonl"
    if log.exists():
        prefix = date.today().strftime("%Y-%m")
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if str(r.get("ts", "")).startswith(prefix):
                runs += 1
                c = float(r.get("cost_usd") or 0)
                total += c
                by_sop[r.get("sop", "?")] = by_sop.get(r.get("sop", "?"), 0.0) + c
    out = [f"Automation spend this month: ${total:.2f}"
           + (f" of a ${cap:.2f} budget ({total / cap * 100:.0f}%)" if cap else "")
           + f" across {runs} run(s)."]
    if by_sop:
        out.append("By task: " + ", ".join(f"{k} ${v:.2f}" for k, v in
                                           sorted(by_sop.items(), key=lambda kv: -kv[1])))
    out.append("Schedules:\n" + ("\n".join(lines) if lines else "(none set up)"))
    return "\n".join(out)


def schema(props, required):
    return {"type": "object",
            "properties": props,
            "required": required}


TOOLS = [
    ("list_sops", "List the user's SOPs (their documented ways of doing recurring business tasks) with status and usage. Call before helping with any business task.", schema({}, []), t_list_sops),
    ("read_sop", "Read one SOP in full. Follow its steps and its 'My way' section when doing the task.", schema({"id": {"type": "string", "description": "The SOP id from list_sops"}}, ["id"]), t_read_sop),
    ("suggest_change", "Record the user's correction or improvement to an SOP. It lands in the SOP's notes for review; you cannot edit SOPs directly.", schema({"id": {"type": "string"}, "suggestion": {"type": "string", "description": "The change, in plain words"}}, ["id", "suggestion"]), t_suggest_change),
    ("create_draft_sop", "Save a NEW draft SOP after the user describes a recurring task and how they do it. Write a complete markdown body with Purpose, When to use, Inputs, Steps (mark owner sign-off points **[APPROVAL]**), My way (their stated preferences), Edge cases.", schema({"id": {"type": "string", "description": "kebab-case id"}, "title": {"type": "string"}, "category": {"type": "string", "description": "e.g. finance, clients, sales, marketing, ops"}, "trigger_phrases": {"type": "string", "description": "comma-separated phrases the user says for this task"}, "content": {"type": "string", "description": "The SOP body markdown (sections only; frontmatter is added automatically)"}}, ["id", "title", "category", "content"]), t_create_draft_sop),
    ("pending_runs", "List automated runs parked at an approval gate, with the prepared work. Use when the user asks what's waiting, or at the start of a check-in.", schema({}, []), t_pending_runs),
    ("resolve_pending", "Record the user's approve/discard decision on a parked run. Approve does NOT execute the action; their next Claude Code session does.", schema({"file": {"type": "string", "description": "pending file name from pending_runs"}, "decision": {"type": "string", "enum": ["approve", "discard"]}, "note": {"type": "string"}}, ["file", "decision"]), t_resolve_pending),
    ("automation_costs", "Report what SOP automation has cost this month vs budget, and which schedules exist, in plain language.", schema({}, []), t_automation_costs),
]


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "smbos", "version": "0.8.0"},
            "instructions": INSTRUCTIONS}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": n, "description": d, "inputSchema": s} for n, d, s, _ in TOOLS]}}
    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        for n, _, _, fn in TOOLS:
            if n == name:
                try:
                    text = fn(params.get("arguments") or {})
                    return {"jsonrpc": "2.0", "id": rid, "result": {
                        "content": [{"type": "text", "text": text}], "isError": False}}
                except Exception as e:
                    return {"jsonrpc": "2.0", "id": rid, "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method and method.startswith("notifications/"):
        return None
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def main():
    sys.stderr.write(f"smbos-mcp serving {D}\n")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
