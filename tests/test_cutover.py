"""Cutover from the legacy daemon to the FastAPI app: plist shape + the migrate/rollback flow.

Stdlib-only (no fastapi import), so these run in the plain `test` job on 3.9 and 3.12.
launchctl, the venv, and the network are all mocked: we assert the orchestration, not the
side effects on a real machine.
"""
import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cutover_dashboard as cut  # noqa: E402
import serve_dashboard as legacy  # noqa: E402


def _parse(xml):
    return plistlib.loads(xml.encode("utf-8"))


def test_app_plist_repoints_label_to_the_app():
    d = _parse(cut.app_plist_xml("/tmp/sops", "/venv/bin/python", port=8765))
    assert d["Label"] == legacy.AGENT_LABEL  # same identity: the bookmark survives
    args = d["ProgramArguments"]
    assert args[0] == "/venv/bin/python"
    assert str(cut.APP) in args
    assert args[args.index("--port") + 1] == "8765"
    assert args[args.index("--sop-dir") + 1] == "/tmp/sops"
    assert d["RunAtLoad"] is True and d["KeepAlive"] is True
    # WatchPaths is dropped on purpose: a watch-restart would drop the live SSE stream.
    assert "WatchPaths" not in d
    # WorkingDirectory matches the legacy daemon (sop_dir) so folder-less runs scope the same.
    assert d["WorkingDirectory"] == "/tmp/sops"
    # launchd's bare PATH would hide the Run-button child (claude/git); we set one.
    assert "/venv/bin" in d["EnvironmentVariables"]["PATH"]


def test_plist_args_are_all_strings():
    # launchd ProgramArguments must be strings; an int port would serialize as <integer>.
    d = _parse(cut.app_plist_xml("/tmp/sops", "/venv/bin/python", port=8765))
    assert all(isinstance(a, str) for a in d["ProgramArguments"])


class _Result:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


def _stub_migrate(monkeypatch, tmp_path, *, prior=None, health=True, port_free=True,
                  compat=(True, ""), venv_exists=True, rollback_load_rc=0,
                  rollback_port_busy=True, configured_port=8765):
    """Wire migrate()'s collaborators to mocks and capture every launchctl call.

    The launchctl stub distinguishes the forward `load` (always ok) from the rollback `load`
    (the 2nd one) so a test can fail JUST the restore and prove migrate reports the dark port.
    """
    plist = tmp_path / "com.smbos.dashboard.plist"
    if prior is not None:
        plist.write_text(prior, encoding="utf-8")
    monkeypatch.setattr(legacy, "plist_path", lambda: plist)
    monkeypatch.setattr(legacy, "dashboard_port", lambda sd: configured_port)

    venv = tmp_path / "python"
    if venv_exists:
        venv.write_text("#!", encoding="utf-8")
    monkeypatch.setattr(cut, "venv_python", lambda *a, **k: venv)

    calls = []
    state = {"loads": 0}

    def fake_launchctl(action, p, *f):
        calls.append((action, f))
        if action == "load":
            state["loads"] += 1
            if state["loads"] >= 2:  # the rollback restore
                return _Result(rollback_load_rc, "already loaded" if rollback_load_rc else "")
        return _Result(0)

    monkeypatch.setattr(cut, "_launchctl", fake_launchctl)
    monkeypatch.setattr(cut, "_kickstart",
                        lambda *a, **k: calls.append(("kickstart", ())) or _Result(0))
    monkeypatch.setattr(cut, "compat_ok", lambda px: compat)
    monkeypatch.setattr(cut, "wait_port_free", lambda *a, **k: port_free)
    monkeypatch.setattr(cut, "wait_port_busy", lambda *a, **k: rollback_port_busy)
    monkeypatch.setattr(cut, "health_ok", lambda *a, **k: health)
    monkeypatch.setattr(cut.lib, "dashboard_token", lambda sd: "tok")
    return plist, calls


def test_migrate_happy_path_writes_app_plist_and_loads(monkeypatch, tmp_path):
    plist, calls = _stub_migrate(monkeypatch, tmp_path)
    ok, msg = cut.migrate(tmp_path / "sops")
    assert ok, msg
    assert "8765" in msg
    d = _parse(plist.read_text(encoding="utf-8"))
    assert str(cut.APP) in d["ProgramArguments"]
    # legacy stopped, app loaded, then kickstarted (a bare load may not start the process).
    assert [a for a, _ in calls] == ["unload", "load", "kickstart"]


def test_migrate_rolls_back_to_legacy_on_failed_health(monkeypatch, tmp_path):
    plist, calls = _stub_migrate(monkeypatch, tmp_path, prior="<LEGACY/>", health=False)
    ok, msg = cut.migrate(tmp_path / "sops")
    assert not ok and "rolled back to the legacy daemon" in msg
    assert plist.read_text(encoding="utf-8") == "<LEGACY/>"  # prior restored verbatim
    assert [a for a, _ in calls[-2:]] == ["load", "kickstart"]  # legacy reloaded + started


def test_migrate_rolls_back_when_port_never_frees(monkeypatch, tmp_path):
    plist, _ = _stub_migrate(monkeypatch, tmp_path, prior="<LEGACY/>", port_free=False)
    ok, msg = cut.migrate(tmp_path / "sops")
    assert not ok and "never freed" in msg
    assert plist.read_text(encoding="utf-8") == "<LEGACY/>"


def test_migrate_honors_a_configured_nondefault_port(monkeypatch, tmp_path):
    # An owner who moved the bookmark off 8765 (dashboard_port in triggers.json) keeps it.
    plist, _ = _stub_migrate(monkeypatch, tmp_path, configured_port=9123)
    ok, msg = cut.migrate(tmp_path / "sops")
    assert ok and "9123" in msg
    d = _parse(plist.read_text(encoding="utf-8"))
    assert d["ProgramArguments"][d["ProgramArguments"].index("--port") + 1] == "9123"


def test_migrate_warns_when_rollback_load_fails(monkeypatch, tmp_path):
    # health fails -> rollback, but the legacy `load` errors (already-loaded/throttled label).
    plist, calls = _stub_migrate(monkeypatch, tmp_path, prior="<LEGACY/>", health=False,
                                 rollback_load_rc=1)
    ok, msg = cut.migrate(tmp_path / "sops")
    assert not ok and "ROLLBACK INCOMPLETE" in msg  # never claim a recovery we didn't get
    # a failed restore load must NOT be followed by kickstart -k (it could revive the bad job)
    assert calls[-1][0] == "load"


def test_migrate_warns_when_port_stays_dark_after_rollback(monkeypatch, tmp_path):
    # legacy `load` returns 0 but nothing rebinds 8765 (busy port / crash loop).
    plist, _ = _stub_migrate(monkeypatch, tmp_path, prior="<LEGACY/>", health=False,
                             rollback_port_busy=False)
    ok, msg = cut.migrate(tmp_path / "sops")
    assert not ok and "ROLLBACK INCOMPLETE" in msg


def test_migrate_reports_when_no_prior_daemon_to_restore(monkeypatch, tmp_path):
    plist, _ = _stub_migrate(monkeypatch, tmp_path, prior=None, health=False)
    ok, msg = cut.migrate(tmp_path / "sops")
    assert not ok and "no prior daemon to roll back to" in msg
    assert not plist.exists()  # our half-written plist was cleaned up


def test_migrate_aborts_when_venv_missing(monkeypatch, tmp_path):
    _stub_migrate(monkeypatch, tmp_path, venv_exists=False)
    ok, msg = cut.migrate(tmp_path / "sops")
    assert not ok and "no venv interpreter" in msg


def test_migrate_aborts_on_schema_incompat(monkeypatch, tmp_path):
    _stub_migrate(monkeypatch, tmp_path, compat=(False, "ImportError: state_store"))
    ok, msg = cut.migrate(tmp_path / "sops")
    assert not ok and "cannot import the shared modules" in msg


def test_compat_ok_passes_for_a_real_interpreter():
    # The system interpreter can import the shared stdlib modules from scripts/.
    ok, err = cut.compat_ok(sys.executable)
    assert ok, err
