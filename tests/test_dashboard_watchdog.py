"""The dashboard watchdog (cron-driven) and its crontab install/remove.

Stdlib-only; launchctl, the socket probe, and crontab are mocked, we assert the orchestration.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cutover_dashboard as cut  # noqa: E402
import dashboard_watchdog as wd  # noqa: E402


def _stub_launchctl(monkeypatch):
    calls = []
    class R:
        returncode = 0
        stdout = ""
        stderr = ""
    monkeypatch.setattr(wd.subprocess, "run", lambda cmd, **k: calls.append(cmd) or R())
    monkeypatch.setattr(wd.lib, "dashboard_port", lambda sd: 8765)
    return calls


def test_watchdog_noop_when_up(monkeypatch, tmp_path):
    calls = _stub_launchctl(monkeypatch)
    monkeypatch.setattr(wd, "port_up", lambda *a, **k: True)
    ok, msg = wd.ensure_up(tmp_path)
    assert ok and "up on 8765" in msg
    assert calls == []  # never touched launchctl while it was already serving


def test_watchdog_kickstarts_when_down(monkeypatch, tmp_path):
    calls = _stub_launchctl(monkeypatch)
    monkeypatch.setattr(wd, "port_up", lambda *a, **k: False)  # down at first check
    monkeypatch.setattr(wd, "_wait_up", lambda *a, **k: True)  # comes up after kickstart
    ok, msg = wd.ensure_up(tmp_path)
    assert ok and "kickstarted" in msg
    assert any(c[:3] == ["launchctl", "kickstart", "-k"] for c in calls)
    assert not any(c[1] == "bootstrap" for c in calls)  # didn't need the fallback


def test_watchdog_bootstrap_fallback_when_not_loaded(monkeypatch, tmp_path):
    calls = _stub_launchctl(monkeypatch)
    monkeypatch.setattr(wd, "port_up", lambda *a, **k: False)
    waits = iter([False, True])  # first kickstart doesn't bring it up; after bootstrap it does
    monkeypatch.setattr(wd, "_wait_up", lambda *a, **k: next(waits))
    ok, msg = wd.ensure_up(tmp_path)
    assert ok and "recovered on 8765" in msg
    assert any(c[1] == "bootstrap" for c in calls)  # fell back to register-then-start


def test_watchdog_reports_still_down(monkeypatch, tmp_path):
    _stub_launchctl(monkeypatch)
    monkeypatch.setattr(wd, "port_up", lambda *a, **k: False)
    monkeypatch.setattr(wd, "_wait_up", lambda *a, **k: False)  # never comes up
    ok, msg = wd.ensure_up(tmp_path)
    assert not ok and "still down" in msg


def test_launchctl_calls_are_bounded(monkeypatch):
    # launchctl runs with a timeout so a hung call can't wedge the cron watchdog
    seen = {}
    monkeypatch.setattr(wd.subprocess, "run",
                        lambda cmd, **k: seen.update(timeout=k.get("timeout")))
    wd._launchctl("kickstart", "-k", "gui/501/label")
    assert isinstance(seen["timeout"], (int, float)) and seen["timeout"] > 0


def test_hung_launchctl_does_not_crash_the_watchdog(monkeypatch, tmp_path):
    # a launchctl that times out (or errors) must be swallowed: the run reports based on the port
    # probe, not a traceback, so the next */5 cron run can retry
    def hang(cmd, **k):
        raise wd.subprocess.TimeoutExpired(cmd, k.get("timeout"))
    monkeypatch.setattr(wd.subprocess, "run", hang)
    monkeypatch.setattr(wd.lib, "dashboard_port", lambda sd: 8765)
    monkeypatch.setattr(wd, "port_up", lambda *a, **k: False)
    monkeypatch.setattr(wd, "_wait_up", lambda *a, **k: False)
    ok, msg = wd.ensure_up(tmp_path)  # must not raise
    assert not ok and "still down" in msg


# --- crontab install/remove (cutover_dashboard, reusing serve_dashboard's helpers) ---

def _stub_cron(monkeypatch, initial="", read_fails=False):
    state = {"text": initial}
    monkeypatch.setattr(cut.legacy, "_read_crontab",
                        lambda: (None if read_fails else state["text"]))
    monkeypatch.setattr(cut.legacy, "_write_crontab",
                        lambda t: (state.__setitem__("text", t), True)[1])
    monkeypatch.setattr(cut.lib, "dashboard_port", lambda sd: 8765)
    return state


def test_install_watchdog_adds_tagged_entry(monkeypatch, tmp_path):
    state = _stub_cron(monkeypatch, initial="0 * * * * other-job  # smbos-inbox-watch\n")
    assert cut.install_watchdog(tmp_path, interval_min=5) is True
    out = state["text"]
    assert "smbos-inbox-watch" in out  # preserved the unrelated entry
    assert cut.WATCHDOG_TAG in out and "--sop-dir" in out and "*/5 * * * *" in out
    assert "--port 8765" in out  # port baked at install time (cron lacks the env var)
    assert str(tmp_path) in out


def test_install_watchdog_is_idempotent(monkeypatch, tmp_path):
    state = _stub_cron(monkeypatch)
    cut.install_watchdog(tmp_path)
    cut.install_watchdog(tmp_path)  # second install must not duplicate
    assert state["text"].count(cut.WATCHDOG_TAG) == 1


def test_install_watchdog_escapes_percent_in_path(monkeypatch, tmp_path):
    # an unescaped % in a cron command becomes a newline; the sop_dir must be escaped
    state = _stub_cron(monkeypatch)
    weird = tmp_path / "My%20SOPs"
    assert cut.install_watchdog(weird) is True
    assert r"My\%20SOPs" in state["text"] and "My%20SOPs" not in state["text"].replace(r"\%", "")


def test_install_watchdog_shell_quotes_special_chars(monkeypatch, tmp_path):
    # a space (or $, quote, backtick) in the path must be shell-quoted, not left bare
    state = _stub_cron(monkeypatch)
    spaced = tmp_path / "My SOPs"
    assert cut.install_watchdog(spaced) is True
    assert "--sop-dir '{}'".format(spaced) in state["text"]  # single-quoted by shlex.quote


def test_install_failure_is_surfaced(monkeypatch, tmp_path, capsys):
    # a crontab that can't be read -> install_watchdog False -> install must warn, not hide it
    monkeypatch.setattr(cut, "env_ready", lambda *a, **k: True)
    monkeypatch.setattr(cut, "ensure_terminal_notifier", lambda *a, **k: None)
    monkeypatch.setattr(cut, "migrate", lambda *a, **k: (True, "flipped"))
    monkeypatch.setattr(cut, "install_watchdog", lambda *a, **k: False)
    monkeypatch.setattr(cut.legacy, "stable_url", lambda sd: "http://127.0.0.1:8765/?t=t")
    cut.main(["install", str(tmp_path)])
    out = capsys.readouterr().out
    assert "won't auto-restart" in out and "http://127.0.0.1:8765" in out


def test_install_watchdog_aborts_when_crontab_unreadable(monkeypatch, tmp_path):
    # a read failure must NOT overwrite the crontab (could wipe the user's other jobs)
    state = _stub_cron(monkeypatch, initial="0 * * * * keep\n", read_fails=True)
    assert cut.install_watchdog(tmp_path) is False
    assert state["text"] == "0 * * * * keep\n"  # untouched


def test_remove_watchdog_drops_only_its_line(monkeypatch, tmp_path):
    state = _stub_cron(monkeypatch, initial="0 * * * * keep  # smbos-inbox-watch\n")
    cut.install_watchdog(tmp_path)
    assert cut.WATCHDOG_TAG in state["text"]
    assert cut.remove_watchdog() is True
    assert cut.WATCHDOG_TAG not in state["text"]
    assert "smbos-inbox-watch" in state["text"]  # the other entry survives
