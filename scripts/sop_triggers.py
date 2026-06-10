#!/usr/bin/env python3
"""Manage SOP triggers: the registry, schedules, and cost reporting.

Usage:
  sop_triggers.py list
  sop_triggers.py add <sop-id> "<spec>" [--model M]   spec: "cron(57 8 * * 1)" or "linear.issue.created[label=bug]"
  sop_triggers.py enable <trigger-id> | disable <trigger-id> | remove <trigger-id>
  sop_triggers.py set <trigger-id> <field> <value>    fields: spec, model, channel, routine_id, notes
  sop_triggers.py sync                                reconcile registry from SOP frontmatter `on:` fields
  sop_triggers.py crontab <trigger-id>                print the crontab line for a cron trigger
  sop_triggers.py costs [--days N]                    spend report from runs.jsonl vs budget
  sop_triggers.py budget [AMOUNT]                     show or set monthly_budget_usd
  sop_triggers.py terminal [terminal|iterm]           which app dashboard launches open (default: auto-detect)
  sop_triggers.py digest show                         build and print today's digest
  sop_triggers.py digest crontab ["M H * * *"]        print the crontab line for the daily digest

Registry lives at <sop-dir>/triggers.json; run log at <sop-dir>/runs.jsonl.
Triggers are created DISABLED; enabling is explicit. Stdlib only.
"""
import json
import re
import shlex
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smbos_lib import iter_sops, parse_frontmatter, resolve_sop_dir

DEFAULT_BUDGET = 20.0


def sop_dir():
    return resolve_sop_dir()


def load(d):
    cfg = d / "triggers.json"
    if cfg.exists():
        return json.loads(cfg.read_text(encoding="utf-8"))
    return {"monthly_budget_usd": DEFAULT_BUDGET, "triggers": []}


def save(d, reg):
    (d / "triggers.json").write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")


def kind_of(spec):
    return "cron" if spec.startswith("cron(") else "event"


def slug(spec):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", spec.lower())).strip("-")[:40]


def find_trigger(reg, tid):
    for t in reg["triggers"]:
        if t["id"] == tid:
            return t
    sys.exit(f"No trigger '{tid}'. Run `list`.")


def upsert(reg, sop, spec, model="sonnet", enabled=False):
    tid = f"{sop}--{slug(spec)}"
    for t in reg["triggers"]:
        if t["id"] == tid:
            return t, False
    t = {"id": tid, "sop": sop, "spec": spec, "kind": kind_of(spec), "enabled": enabled,
         "model": model, "channel": "local-cron" if kind_of(spec) == "cron" else "webhook",
         "routine_id": None, "created": date.today().isoformat(), "notes": ""}
    reg["triggers"].append(t)
    return t, True


def cmd_list(d, reg):
    if not reg["triggers"]:
        print("No triggers. Add one with: sop_triggers.py add <sop-id> \"cron(57 8 * * 1)\"")
        return
    for t in reg["triggers"]:
        state = "ON " if t["enabled"] else "off"
        print(f"[{state}] {t['id']}  sop={t['sop']}  {t['spec']}  kind={t['kind']} "
              f"channel={t['channel']} model={t['model']}"
              + (f" routine={t['routine_id']}" if t.get("routine_id") else ""))


def cmd_sync(d, reg):
    found = 0
    for p in iter_sops(d):
        meta = parse_frontmatter(p.read_text(encoding="utf-8")[:1200])
        sop = meta.get("id") or p.stem
        if not meta.get("on"):
            continue
        for spec in [s.strip() for s in meta["on"].split(",") if s.strip()]:
            t, created = upsert(reg, sop, spec)
            found += 1
            if created:
                print(f"added (disabled): {t['id']}")
    print(f"sync done: {found} on: spec(s) found across SOPs.")


def cmd_crontab(d, t, plugin_root):
    if t["kind"] != "cron":
        sys.exit(f"'{t['id']}' is an event trigger; crontab does not apply.")
    expr = t["spec"][5:-1].strip()
    runner = plugin_root / "scripts" / "run_sop.py"
    extra = f" --inputs {shlex.quote(t['inputs'])}" if t.get("inputs") else ""
    print(f"{expr} /usr/bin/env python3 {runner} {t['sop']} --source cron --model {t['model']}{extra} "
          f">> {d}/trigger.log 2>&1")


def cmd_costs(d, reg, days):
    log = d / "runs.jsonl"
    if not log.exists():
        print("No runs logged yet.")
        return
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    month_prefix = date.today().strftime("%Y-%m")
    by_sop, month_total, recent = {}, 0.0, []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        cost = float(r.get("cost_usd") or 0)
        ts = str(r.get("ts", ""))
        if ts.startswith(month_prefix):
            month_total += cost
        try:
            t = datetime.fromisoformat(ts).timestamp()
        except ValueError:
            continue
        if t >= cutoff:
            s = by_sop.setdefault(r.get("sop", "?"), {"runs": 0, "cost": 0.0, "parked": 0, "errors": 0})
            s["runs"] += 1
            s["cost"] += cost
            s["parked"] += r.get("result") == "parked"
            s["errors"] += r.get("result") == "error"
            recent.append(r)
    cap = float(reg.get("monthly_budget_usd") or 0)
    pct = f" ({month_total / cap * 100:.0f}% of ${cap:.2f} budget)" if cap else ""
    print(f"This month: ${month_total:.2f}{pct}")
    print(f"\nLast {days} days by SOP:")
    for sop, s in sorted(by_sop.items(), key=lambda kv: -kv[1]["cost"]):
        print(f"  {sop}: {s['runs']} runs, ${s['cost']:.2f}, {s['parked']} parked, {s['errors']} errors")
    print("\nLast 5 runs:")
    for r in recent[-5:]:
        c = r.get("cost_usd")
        print(f"  {r.get('ts', '')[:16]} {r.get('sop')} [{r.get('result')}] "
              f"{'$%.4f' % c if isinstance(c, (int, float)) else '-'} {(r.get('note') or '')[:60]}")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    d = sop_dir()
    reg = load(d)
    cmd = args[0]
    plugin_root = Path(__file__).resolve().parent.parent

    if cmd == "list":
        cmd_list(d, reg)
    elif cmd == "add" and len(args) >= 3:
        model = args[args.index("--model") + 1] if "--model" in args else "sonnet"
        t, created = upsert(reg, args[1], args[2], model=model)
        save(d, reg)
        print(("added (disabled): " if created else "already exists: ") + t["id"])
    elif cmd in ("enable", "disable") and len(args) >= 2:
        t = find_trigger(reg, args[1])
        t["enabled"] = cmd == "enable"
        save(d, reg)
        print(f"{t['id']} {'enabled' if t['enabled'] else 'disabled'}."
              + (" Remember: enabling here does not install the schedule; see `crontab` or the cloud routine."
                 if t["kind"] == "cron" else ""))
    elif cmd == "remove" and len(args) >= 2:
        t = find_trigger(reg, args[1])
        reg["triggers"].remove(t)
        save(d, reg)
        print(f"removed {t['id']}")
    elif cmd == "set" and len(args) >= 4:
        t = find_trigger(reg, args[1])
        if args[2] not in ("spec", "model", "channel", "routine_id", "notes", "inputs"):
            sys.exit("settable fields: spec, model, channel, routine_id, notes, inputs")
        t[args[2]] = args[3]
        if args[2] == "spec":
            t["kind"] = kind_of(args[3])
        save(d, reg)
        print(f"{t['id']}.{args[2]} = {args[3]}")
    elif cmd == "sync":
        cmd_sync(d, reg)
        save(d, reg)
    elif cmd == "crontab" and len(args) >= 2:
        cmd_crontab(d, find_trigger(reg, args[1]), plugin_root)
    elif cmd == "costs":
        days = int(args[args.index("--days") + 1]) if "--days" in args else 30
        cmd_costs(d, reg, days)
    elif cmd == "budget":
        if len(args) >= 2:
            reg["monthly_budget_usd"] = float(args[1])
            save(d, reg)
        print(f"monthly_budget_usd = {reg.get('monthly_budget_usd')}")
    elif cmd == "terminal":
        if len(args) >= 2:
            if args[1] not in ("terminal", "iterm"):
                sys.exit("supported: terminal, iterm")
            reg["terminal"] = args[1]
            save(d, reg)
        print(f"terminal = {reg.get('terminal') or '(auto-detect from the session that starts the dashboard)'}")
    elif cmd == "digest" and len(args) >= 2:
        runner = plugin_root / "scripts" / "digest.py"
        if args[1] == "show":
            subprocess.run([sys.executable, str(runner), "--sop-dir", str(d), "--print-only"])
        elif args[1] == "crontab":
            expr = args[2] if len(args) > 2 else "53 7 * * *"
            print(f"{expr} /usr/bin/env python3 {runner} --sop-dir {d} >> {d}/trigger.log 2>&1")
        else:
            sys.exit("digest subcommands: show, crontab")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
