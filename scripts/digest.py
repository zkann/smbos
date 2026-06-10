#!/usr/bin/env python3
"""SmbOS daily digest: what's waiting, what ran, what it cost, what failed.

Deterministic and token-free: reads pending/, runs.jsonl, and triggers.json,
writes <sop-dir>/DIGEST.md, and delivers via configured channels. Plain
language throughout.

Usage: digest.py [--sop-dir DIR] [--print-only]
Delivery (config block "digest" in triggers.json, all optional):
  {"digest": {"slack_webhook_url": "https://hooks.slack.com/...", "notify": true}}
notify=true posts a macOS notification (default true when unset).
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path  # noqa: F401  (used for project-folder display)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import humanize_failure, humanize_source, humanize_spec


def resolve_sop_dir(explicit):
    for c in [explicit, os.environ.get("SOP_DIR"), str(Path.home() / "sops")]:
        if c and Path(c).expanduser().is_dir():
            return Path(c).expanduser()
    sys.exit("No SOP directory found.")


def frontmatter_value(text, field):
    for line in text[:800].splitlines():
        if line.startswith(field + ":"):
            return line.partition(":")[2].strip()
    return None


def build(d):
    now = datetime.now(timezone.utc)
    lines = [f"# Your business, {date.today().strftime('%A %B %-d')}", ""]

    # Waiting for approval
    waiting = []
    pdir = d / "pending"
    if pdir.is_dir():
        for p in sorted(pdir.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            if frontmatter_value(text, "status") == "pending":
                sop = frontmatter_value(text, "sop") or p.stem
                src = frontmatter_value(text, "trigger_source") or "?"
                waiting.append(f"- **{sop}** prepared work and is waiting for your OK "
                               f"(started by {humanize_source(src)})")
    if waiting:
        lines += [f"## Waiting for you ({len(waiting)})", ""] + waiting + \
                 ["", 'Say "review my pending runs" in Claude (Code or Desktop) to approve or discard.', ""]
    else:
        lines += ["Nothing is waiting for your approval.", ""]

    # Owner-queued tasks for the next interactive session
    qdir = d / "queue"
    queued = []
    if qdir.is_dir():
        for p in sorted(qdir.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            if frontmatter_value(text, "status") == "queued":
                sop = frontmatter_value(text, "sop") or p.stem
                proj = frontmatter_value(text, "project") or ""
                where = f" (in {Path(proj).name})" if proj else ""
                queued.append(f"- **{sop}**{where}")
    if queued:
        lines += [f"## On your plate ({len(queued)})", ""] + queued + \
                 ["", "These start the next time you open Claude in the matching folder; they need you in the loop.", ""]

    # Last 7 days of automation
    log = d / "runs.jsonl"
    week, failures = [], []
    month_total = 0.0
    month_prefix = date.today().strftime("%Y-%m")
    if log.exists():
        cutoff = now - timedelta(days=7)
        for raw in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(raw)
                ts = datetime.fromisoformat(r["ts"])
            except (ValueError, KeyError):
                continue
            if str(r.get("ts", "")).startswith(month_prefix):
                month_total += float(r.get("cost_usd") or 0)
            if ts >= cutoff:
                week.append(r)
                if r.get("result") == "error":
                    failures.append(r)
    if week:
        ok = sum(1 for r in week if r.get("result") in ("ok", "parked"))
        cost = sum(float(r.get("cost_usd") or 0) for r in week)
        lines += ["## Automation this week", "",
                  f"- {len(week)} run(s); {ok} went fine, {len(failures)} had problems.",
                  f"- Spent ${cost:.2f} this week, ${month_total:.2f} so far this month."]
        cap = 0.0
        cfg_path = d / "triggers.json"
        if cfg_path.exists():
            try:
                cap = float(json.loads(cfg_path.read_text(encoding="utf-8")).get("monthly_budget_usd") or 0)
            except (ValueError, TypeError):
                pass
        if cap:
            pct = month_total / cap * 100
            lines.append(f"- That's {pct:.0f}% of your ${cap:.0f} monthly cap."
                         + (" Worth a look." if pct >= 80 else ""))
        lines.append("")
    if failures:
        lines += ["## Needs attention", ""]
        for r in failures[-5:]:
            plain, action = humanize_failure(r.get("note"))
            when = str(r.get("ts", ""))[:10]
            lines.append(f"- **{r.get('sop')}** ({when}): {plain}. To fix: {action}.")
        lines.append("")

    # Schedules
    cfg_path = d / "triggers.json"
    if cfg_path.exists():
        try:
            reg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except ValueError:
            reg = {}
        active = [t for t in reg.get("triggers", []) if t.get("enabled")]
        if active:
            lines += ["## On the calendar", ""]
            lines += [f"- {t['sop']}: {humanize_spec(t['spec'], t.get('kind'))}" for t in active]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n", len(waiting), len(failures)


def deliver(d, text, n_waiting, n_failures):
    cfg = {}
    cfg_path = d / "triggers.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8")).get("digest") or {}
        except ValueError:
            pass
    out = d / "DIGEST.md"
    out.write_text(text, encoding="utf-8")
    delivered = [str(out)]
    url = cfg.get("slack_webhook_url")
    if url:
        try:
            req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15)
            delivered.append("slack")
        except OSError as e:
            delivered.append(f"slack failed: {e}")
    if cfg.get("notify", True) and sys.platform == "darwin":
        summary = (f"{n_waiting} waiting for your OK" if n_waiting else "nothing waiting") + \
                  (f", {n_failures} thing(s) need attention" if n_failures else "")
        try:
            subprocess.run(["osascript", "-e",
                            f'display notification "{summary}" with title "SmbOS digest"'],
                           capture_output=True, timeout=10)
            delivered.append("notification")
        except (OSError, subprocess.TimeoutExpired):
            pass
    return delivered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sop-dir")
    ap.add_argument("--print-only", action="store_true")
    args = ap.parse_args()
    d = resolve_sop_dir(args.sop_dir)
    text, n_waiting, n_failures = build(d)
    if args.print_only:
        print(text)
        return
    delivered = deliver(d, text, n_waiting, n_failures)
    print(f"digest written ({', '.join(delivered)})")


if __name__ == "__main__":
    main()
