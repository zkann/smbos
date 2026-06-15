#!/usr/bin/env python3
"""Generate the SmbOS dashboard: a self-contained HTML view of the SOP library.

Usage: generate_dashboard.py [sop_dir]
SOP directory resolution: argv[1] > $SOP_DIR > ./sops > ~/sops
Writes <sop_dir>/dashboard.html and prints its path. No network, stdlib only.
For the interactive live mode, see serve_dashboard.py.
"""
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import humanize_failure, humanize_source, humanize_spec
from smbos_lib import RUNTIME_DIRS as NON_SOP_DIRS
from smbos_lib import SKIP_NAMES, active_runs, is_drifted, parse_frontmatter, split_frontmatter
from smbos_lib import resolve_sop_dir as lib_resolve_sop_dir


def resolve_sop_dir():
    return lib_resolve_sop_dir(explicit=sys.argv[1] if len(sys.argv) > 1 else None, use_cwd=True)


def collect(sop_dir):
    files = []
    for p in sorted(sop_dir.rglob("*.md")):
        rel_parts = p.relative_to(sop_dir).parts
        if p.name in SKIP_NAMES or p.name.startswith(".") or any(d in NON_SOP_DIRS for d in rel_parts):
            continue
        rel = p.relative_to(sop_dir).as_posix()
        try:
            content = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        meta, body = split_frontmatter(content)
        files.append({"path": rel, "content": content,
                      "drift": is_drifted(meta, body)})
    return files


def collect_pending(sop_dir):
    items = []
    pdir = sop_dir / "pending"
    if pdir.is_dir():
        for p in sorted(pdir.glob("*.md")):
            try:
                content = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            src = None
            for line in content[:600].splitlines():
                if line.startswith("trigger_source:"):
                    src = line.partition(":")[2].strip()
            items.append({"path": p.name, "content": content,
                          "source_plain": humanize_source(src) if src else "an automated run"})
    return items


def collect_queued(sop_dir):
    out = []
    qdir = sop_dir / "queue"
    if qdir.is_dir():
        for p in sorted(qdir.glob("*.md")):
            m = parse_frontmatter(p.read_text(encoding="utf-8"))
            if m.get("status") != "queued":
                continue
            out.append({"sop": m.get("sop", p.stem), "file": p.name,
                        "project": Path(m["project"]).name if m.get("project") else ""})
    return out


def work_items(sop_dir):
    out = []
    wd = sop_dir / "work"
    if not wd.is_dir():
        return out
    for p in sorted(wd.glob("*.md")):
        m = parse_frontmatter(p.read_text(encoding="utf-8"))
        if m.get("status") == "done":
            continue
        out.append({"title": m.get("title", p.stem),
                    "stages": [s.strip() for s in m.get("stages", "").split(",") if s.strip()],
                    "stage": m.get("stage", ""), "status": m.get("status", "active"),
                    "project": Path(m["project"]).name if m.get("project") else "",
                    "updated": (m.get("updated", "") or "")[:10]})
    return out


def schedules(sop_dir):
    cfg = sop_dir / "triggers.json"
    out = {}
    if cfg.exists():
        try:
            reg = json.loads(cfg.read_text(encoding="utf-8"))
        except ValueError:
            return out
        for t in reg.get("triggers", []):
            if t.get("enabled"):
                out.setdefault(t["sop"], []).append(humanize_spec(t["spec"], t.get("kind")))
    return out


def recent_failures(sop_dir, days=7):
    log = sop_dir / "runs.jsonl"
    out = []
    if not log.exists():
        return out
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            ts = datetime.fromisoformat(r["ts"]).timestamp()
        except (ValueError, KeyError):
            continue
        if ts >= cutoff and r.get("result") == "error":
            plain, action = humanize_failure(r.get("note"))
            out.append({"sop": r.get("sop"), "when": str(r.get("ts", ""))[:10],
                        "plain": plain, "action": action})
    return out[-5:]


def cost_summary(sop_dir):
    out = {"month_total": 0.0, "budget": 0.0, "runs": 0, "parked": 0}
    cfg = sop_dir / "triggers.json"
    if cfg.exists():
        try:
            out["budget"] = float(json.loads(cfg.read_text(encoding="utf-8")).get("monthly_budget_usd") or 0)
        except (ValueError, TypeError):
            pass
    log = sop_dir / "runs.jsonl"
    if log.exists():
        prefix = date.today().strftime("%Y-%m")
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if str(r.get("ts", "")).startswith(prefix):
                out["runs"] += 1
                out["month_total"] += float(r.get("cost_usd") or 0)
                out["parked"] += r.get("result") == "parked"
    return out


def build_html(sop_dir, cfg=None):
    # The generator is the bundler: three source files, one self-contained output.
    assets = Path(__file__).resolve().parent.parent / "assets"
    html = (assets / "index.html").read_text(encoding="utf-8")
    html = html.replace("/*__STYLE__*/", (assets / "style.css").read_text(encoding="utf-8"))
    html = html.replace("/*__APP_JS__*/", (assets / "app.js").read_text(encoding="utf-8"))
    data = json.dumps(collect(sop_dir)).replace("</", "<\\/")
    cfg_json = json.dumps(cfg or {"live": False}).replace("</", "<\\/")
    extra = json.dumps({"pending": collect_pending(sop_dir), "costs": cost_summary(sop_dir),
                        "schedules": schedules(sop_dir),
                        "failures": recent_failures(sop_dir),
                        "work": work_items(sop_dir),
                        "queued": collect_queued(sop_dir),
                        "runs": active_runs(sop_dir)}).replace("</", "<\\/")
    html = html.replace("__SOPS_JSON__", data)
    html = html.replace("__CFG_JSON__", cfg_json)
    html = html.replace("__EXTRA_JSON__", extra)
    html = html.replace("__GENERATED__", datetime.now(timezone.utc).isoformat())
    display_dir = str(sop_dir)
    home = str(Path.home())
    if display_dir == home or display_dir.startswith(home + os.sep):
        display_dir = "~" + display_dir[len(home):]
    html = html.replace("__SOP_DIR__", display_dir)
    return html


def ensure_gitignore(sop_dir):
    gi = sop_dir / ".gitignore"
    line = "dashboard.html"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if line not in existing.splitlines():
        with gi.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(line + "\n")


def main():
    sop_dir = resolve_sop_dir()
    out = sop_dir / "dashboard.html"
    out.write_text(build_html(sop_dir), encoding="utf-8")
    if (sop_dir / ".git").exists():
        ensure_gitignore(sop_dir)
    print(out)


if __name__ == "__main__":
    main()
