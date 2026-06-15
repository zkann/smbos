import plistlib
import sys

import serve_dashboard as sv


def test_token_persists_and_rotates(tmp_path):
    t1 = sv.get_or_create_token(tmp_path)
    assert t1 and sv.get_or_create_token(tmp_path) == t1  # stable
    import stat, os
    assert stat.S_IMODE(os.stat(tmp_path / sv.TOKEN_FILE).st_mode) == 0o600
    t2 = sv.rotate_token(tmp_path)
    assert t2 != t1 and sv.get_or_create_token(tmp_path) == t2  # new + now stable


def test_port_resolution(tmp_path, monkeypatch):
    monkeypatch.delenv("SMBOS_DASHBOARD_PORT", raising=False)
    assert sv.dashboard_port(tmp_path) == sv.DEFAULT_PORT
    (tmp_path / "triggers.json").write_text('{"dashboard_port": 9001}')
    assert sv.dashboard_port(tmp_path) == 9001
    monkeypatch.setenv("SMBOS_DASHBOARD_PORT", "9100")  # env wins
    assert sv.dashboard_port(tmp_path) == 9100


def test_stable_url_format(tmp_path, monkeypatch):
    monkeypatch.delenv("SMBOS_DASHBOARD_PORT", raising=False)
    u = sv.stable_url(tmp_path)
    assert u.startswith("http://127.0.0.1:%d/?t=" % sv.DEFAULT_PORT)
    assert u == sv.stable_url(tmp_path)  # deterministic


def test_plist_is_valid_and_correct(tmp_path):
    d = plistlib.loads(sv._plist_xml(tmp_path).encode())
    assert d["Label"] == sv.AGENT_LABEL
    assert d["ProgramArguments"][-1] == "--serve"
    assert str(tmp_path) in d["ProgramArguments"]
    assert d["KeepAlive"] is True and d["RunAtLoad"] is True
    names = [p.split("/")[-1] for p in d["WatchPaths"]]
    assert "scripts" in names and "assets" in names  # restart on code update


def test_install_uninstall_agent(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sv, "plist_path", lambda: tmp_path / "com.smbos.dashboard.plist")
    monkeypatch.setattr(sv.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or type("R", (), {"returncode": 0, "stderr": ""})())
    ok, msg = sv.install_agent(tmp_path)
    assert ok and (tmp_path / "com.smbos.dashboard.plist").exists()
    assert any("load" in c for c in calls)
    assert sv.uninstall_agent() is True
    assert not (tmp_path / "com.smbos.dashboard.plist").exists()
    assert sv.uninstall_agent() is False  # already gone


def test_install_reports_launchctl_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(sv, "plist_path", lambda: tmp_path / "a.plist")
    monkeypatch.setattr(sv.subprocess, "run",
                        lambda cmd, **kw: type("R", (), {"returncode": 1, "stderr": "boom"})())
    ok, msg = sv.install_agent(tmp_path)
    assert ok is False and "boom" in msg
