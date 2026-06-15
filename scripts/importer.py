"""Idempotent importer: backfill work-state tasks from a source into the state store.

A domain's existing records (a JSONL export, a log) are mapped to tasks and upserted by
(domain, source_ref), so re-running never duplicates and a run interrupted partway is safe
to re-run: it updates the rows already imported and fills in the rest. Per-record errors
(a record missing a subject, a malformed JSON line) are collected and skipped, not fatal,
so one bad row doesn't block the import.

Generic by design: this public module ships the mechanism plus a default record->task
mapping. A specific domain supplies its own records (and, if needed, its own mapping); the
private particulars never live here.

Stdlib only, Python 3.9+.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow `python3 scripts/importer.py`
import smbos_lib as lib
import state_store as ss


def map_record(record, domain, source_key="id", kind_default="item"):
    """Map one source record (a dict) to upsert_task kwargs. Raises ValueError if unusable.

    Requires a non-empty `subject`. `source_ref` comes from `record[source_key]` (the stable
    id that makes re-import idempotent); if absent, the task is imported un-deduped (NULL
    source_ref). `priority` must be int-coercible.
    """
    if not isinstance(record, dict):
        raise ValueError("record is not a JSON object")
    subject = record.get("subject")
    if not subject:
        raise ValueError("record missing non-empty 'subject'")
    try:
        priority = int(record.get("priority", 0))
    except (TypeError, ValueError):
        raise ValueError(f"priority is not an integer: {record.get('priority')!r}")
    source = record.get(source_key)
    return {
        "domain": domain,
        "kind": str(record.get("kind", kind_default)),
        "subject": str(subject),
        "status": str(record.get("status", "waiting")),
        "priority": priority,
        "source_ref": None if source is None else str(source),
    }


def import_records(sop_dir, domain, records, source_key="id", kind_default="item"):
    """Upsert an iterable of record dicts as tasks. Returns {'imported': n, 'errors': [...]}."""
    imported, errors = 0, []
    for i, record in enumerate(records):
        try:
            ss.upsert_task(sop_dir, **map_record(record, domain, source_key, kind_default))
            imported += 1
        except (ValueError, ss.StateStoreError) as exc:
            errors.append(f"record {i}: {exc}")
    return {"imported": imported, "errors": errors}


def import_jsonl(sop_dir, domain, path, source_key="id", kind_default="item"):
    """Import one record per line from a JSONL file. Malformed lines are skipped + reported."""
    imported, errors = 0, []
    with open(path, encoding="utf-8") as fh:
        for ln, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"line {ln}: bad JSON: {exc}")
                continue
            try:
                ss.upsert_task(sop_dir, **map_record(record, domain, source_key, kind_default))
                imported += 1
            except (ValueError, ss.StateStoreError) as exc:
                errors.append(f"line {ln}: {exc}")
    return {"imported": imported, "errors": errors}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import domain records (JSONL) into the work-state store as tasks.")
    ap.add_argument("--sop-dir", default=None)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--jsonl", required=True, help="path to a JSONL file, one record per line")
    ap.add_argument("--source-key", default="id", help="record field used as the stable source_ref (default: id)")
    ap.add_argument("--kind-default", default="item")
    args = ap.parse_args(argv)
    sop_dir = lib.resolve_sop_dir(args.sop_dir)
    result = import_jsonl(sop_dir, args.domain, args.jsonl, args.source_key, args.kind_default)
    print(f"imported {result['imported']} task(s) into domain {args.domain!r}")
    for err in result["errors"]:
        print(f"  skipped: {err}", file=sys.stderr)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
