"""Plain-language rendering of SmbOS system state. Spec syntax stays in files."""
import re

SOURCES = {
    "cron": "its schedule",
    "manual": "a manual test",
    "linear": "a Linear event",
    "slack": "a Slack message",
    "webhook": "a webhook",
}


def humanize_cron(spec):
    s = spec.strip()
    if s.startswith("cron(") and s.endswith(")"):
        s = s[5:-1].strip()
    parts = s.split()
    if len(parts) != 5:
        return spec
    minute, hour, dom, _, dow = parts
    days = {"0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
            "4": "Thursday", "5": "Friday", "6": "Saturday", "7": "Sunday",
            "1-5": "weekday"}
    try:
        t = f"{int(hour) % 12 or 12}:{int(minute):02d} {'AM' if int(hour) < 12 else 'PM'}"
    except ValueError:
        return spec
    day = days.get(dow)
    if day:
        return f"every {day} at {t}"
    if dow != "*":
        return spec
    if dom != "*":
        return f"monthly on day {dom} at {t}"
    return f"every day at {t}"


def humanize_spec(spec, kind=None):
    if spec.startswith("cron(") or kind == "cron":
        return humanize_cron(spec)
    m = re.match(r"(\w+)\.([\w.]+)(?:\[(.+)\])?", spec)
    if m:
        svc, event, cond = m.groups()
        s = f"when a {svc.title()} {event.replace('.', ' ').replace('_', ' ')} happens"
        return s + (f" ({cond})" if cond else "")
    return spec


def humanize_source(source):
    return SOURCES.get(source, f"a {source} event")


def humanize_failure(note):
    """Map a raw run-failure note to (plain explanation, suggested action)."""
    n = (note or "").lower()
    if "budget reached" in n:
        return ("automation hit its monthly spending cap",
                "raise the budget if this was expected (say: set my automation budget)")
    if "unrecorded changes" in n:
        return ("its steps were changed outside the normal save flow, so it won't run on its own",
                "ask Claude to review the changes; recording them restores running")
    if "status is 'draft'" in n or "drafts need a human" in n:
        return ("this task hasn't been done with you yet, so it won't run on its own",
                "do it once together in Claude Code and automation unlocks")
    if any(k in n for k in ("oauth", "api key", "authentication", "login", "logged in",
                            "socket connection was closed", "401")):
        return ("Claude wasn't logged in on this computer",
                "open Claude Code once and log in; it will fix itself")
    if "rate limit" in n or "429" in n or "usage limit" in n:
        return ("Claude was at its usage limit at the time",
                "nothing to do; the next scheduled run should work")
    if "timeout" in n or "timed out" in n:
        return ("the run took too long and was stopped",
                "try it manually in Claude Code to see where it gets stuck")
    if "overloaded" in n or "529" in n:
        return ("Claude's service was briefly overloaded",
                "nothing to do; the next scheduled run should work")
    return ("the run hit an unexpected error",
            f"ask Claude Code to look into it (detail: {(note or '')[:120]})")
