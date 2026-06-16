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


def test_record_makes_fallback_port_discoverable(tmp_path, monkeypatch):
    import json, stat, os
    # a server that fell back to a random port writes its actual port/token
    sv.write_server_record(tmp_path, 51234, "tok-abc")
    rec = tmp_path / sv.SERVER_FILE
    assert json.loads(rec.read_text())["port"] == 51234
    assert stat.S_IMODE(os.stat(rec).st_mode) == 0o600
    # live_server_url pings the RECORDED port (not the fixed one) first
    monkeypatch.setattr(sv, "_ping", lambda port, tok: port == 51234 and tok == "tok-abc")
    assert sv.live_server_url(tmp_path) == "http://127.0.0.1:51234/?t=tok-abc"
    # nothing answering -> stale record cleared, None
    monkeypatch.setattr(sv, "_ping", lambda port, tok: False)
    assert sv.live_server_url(tmp_path) is None
    assert not rec.exists()


def test_clear_own_record_respects_pid(tmp_path):
    import json, os
    rec = tmp_path / sv.SERVER_FILE
    rec.write_text(json.dumps({"port": 1, "token": "x", "pid": os.getpid()}))
    sv.clear_own_server_record(tmp_path)
    assert not rec.exists()
    rec.write_text(json.dumps({"port": 1, "token": "x", "pid": 999999}))  # someone else's
    sv.clear_own_server_record(tmp_path)
    assert rec.exists()  # left alone


def test_plist_has_working_directory_and_resolves(tmp_path):
    import plistlib
    d = plistlib.loads(sv._plist_xml(tmp_path).encode())
    assert d["WorkingDirectory"] == str(tmp_path)  # launchd cwd is sane, not /


def test_daemon_serve_routes_run_anywhere(tmp_path, monkeypatch):
    # in daemon mode LAUNCH_CWD becomes the library so routing is run-anywhere,
    # regardless of launchd's actual cwd
    monkeypatch.setattr(sv, "LAUNCH_CWD", "/")  # simulate launchd cwd
    monkeypatch.setattr(sv, "get_or_create_token", lambda d: "t")
    # stub the serve loop so we only exercise the setup
    class FakeSrv:
        def serve_forever(self): raise KeyboardInterrupt
    monkeypatch.setattr(sv, "ThreadingHTTPServer", lambda *a, **k: FakeSrv())
    monkeypatch.setattr(sv, "write_server_record", lambda *a: None)
    sv.serve(tmp_path, daemon=True)
    assert sv.LAUNCH_CWD == str(tmp_path)  # not "/"


def test_install_redirects_with_resolved_path(tmp_path, monkeypatch):
    # install now redirects to the cutover installer; main() must still resolve a relative
    # SOP path to absolute so the printed command is runnable as-is.
    import pytest
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sops").mkdir()
    monkeypatch.setattr(sv.sys, "argv", ["serve_dashboard.py", "sops", "install"])
    with pytest.raises(SystemExit) as e:
        sv.main()
    assert "cutover_dashboard.py" in str(e.value)
    assert str(tmp_path / "sops") in str(e.value)  # absolute, not the relative "sops"
