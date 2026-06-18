"""Owner settings read + apply-on-change write, shared (stdlib-only) by the FastAPI dashboard and the
engine-action CLI the broker invokes. The terminal field is env-detected (preferred_terminal), so
this is the one endpoint that reflects the SERVING process's environment -- via the engine it reflects
the desktop app's (no TERM_PROGRAM -> Terminal.app default), configurable by the owner."""

import fcntl
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import serve_dashboard as legacy


class BadSetting(Exception):
    """Unknown setting key -> 400."""


# Per-setting writers (reuse the daemon's validators; each raises ValueError on a bad value).
_SETTERS = {
    "launch_permission": legacy.set_launch_permission,
    "terminal": legacy.set_terminal,
    "budget": legacy.set_budget,
}


def _month_to_date(sop_dir):
    """Current-UTC-month spend from runs.jsonl (mirrors dashboard_app._cost_estimates' month_to_date)."""
    total = 0.0
    prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        lines = (Path(sop_dir) / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0.0
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        cost = r.get("cost_usd")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            continue
        if str(r.get("ts", "")).startswith(prefix):
            total += cost
    return round(total, 2)


def read_settings(sop_dir):
    """Current owner config for the Settings panel (mirrors dashboard_app._settings)."""
    sop_dir = Path(sop_dir)  # the legacy readers expect a Path (the engine passes a str arg)
    budget = 0.0
    try:
        tj = json.loads((Path(sop_dir) / "triggers.json").read_text(encoding="utf-8"))
        if isinstance(tj, dict):
            parsed = float(tj.get("monthly_budget_usd") or 0)
            budget = parsed if (math.isfinite(parsed) and parsed >= 0) else 0.0  # defensive vs a bad stored value
    except (OSError, ValueError, TypeError):
        pass
    return {
        "launch_permission": legacy.launch_permission(sop_dir),  # trust / ask / skip
        "terminal": legacy.preferred_terminal(sop_dir),          # terminal / iterm (env-detected)
        "budget": budget,
        "spent": _month_to_date(sop_dir),                        # month-to-date, for budget headroom
    }


def write_setting(sop_dir, key, value):
    """Apply one setting (key/value) and return the full new state. Raises BadSetting (unknown key) /
    ValueError (bad value) / OSError (write failed)."""
    sop_dir = Path(sop_dir)  # the legacy setters expect a Path (the engine passes a str arg)
    setter = _SETTERS.get(str(key or ""))
    if setter is None:
        raise BadSetting("unknown setting")
    # Serialize the triggers.json read-modify-replace across PROCESSES: FastAPI used an in-process
    # asyncio.Lock, but the engine is a fresh process per request, so an flock is what stops two
    # concurrent setting writes from each reading the old file and the later replace dropping the earlier.
    locks = Path(sop_dir) / "triggers"
    locks.mkdir(exist_ok=True)
    with open(locks / ".settings.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        setter(sop_dir, value)
        return {"settings": read_settings(sop_dir)}  # echo the full new state so the SPA syncs
