"""Unit tests for the Electron/broker cutover installer. The launchctl + health plumbing is
monkeypatched, so these never touch the real login items or ports."""
import plistlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cutover_desktop as cd       # noqa: E402
import cutover_dashboard as fa     # noqa: E402


class _R:
    def __init__(self, rc=0, err=""):
        self.returncode = rc
        self.stderr = err


def test_desktop_plist_xml_shape(tmp_path):
    xml = cd.desktop_plist_xml(tmp_path, 8765, electron_bin=Path("/x/electron"))
    spec = plistlib.loads(xml.encode("utf-8"))
    assert spec["Label"] == "com.smbos.desktop"                       # its OWN label, not the FastAPI one
    assert spec["ProgramArguments"] == ["/x/electron", str(cd.DESKTOP)]  # runs electron <desktop/>
    assert spec["EnvironmentVariables"]["SMBOS_BROKER_PORT"] == "8765"  # the port the broker BINDS
    assert spec["EnvironmentVariables"]["SMBOS_DASHBOARD_PORT"] == "8765"  # == targetPort, so the guard fires
    assert spec["EnvironmentVariables"]["SOP_DIR"] == str(tmp_path)
    assert spec["WorkingDirectory"] == str(tmp_path)                  # folder-less runs inherit it
    assert spec["RunAtLoad"] is True
    assert spec["KeepAlive"] == {"SuccessfulExit": False}             # restart a crash, not a clean Quit
    assert "/opt/homebrew/bin" in spec["EnvironmentVariables"]["PATH"]  # engine children resolve claude/git


def test_env_ready(tmp_path, monkeypatch):
    elec = tmp_path / "node_modules" / ".bin" / "electron"
    dist = tmp_path / "frontend" / "dist" / "index.html"
    monkeypatch.setattr(cd, "ELECTRON_BIN", elec)
    monkeypatch.setattr(cd, "FRONTEND", tmp_path / "frontend")
    assert cd.env_ready() is False              # nothing built
    elec.parent.mkdir(parents=True)
    elec.write_text("")
    assert cd.env_ready() is False              # electron present, SPA missing
    dist.parent.mkdir(parents=True)
    dist.write_text("<html></head>")
    assert cd.env_ready() is True               # both present


def test_migrate_needs_electron(tmp_path):
    ok, msg = cd.migrate(tmp_path, port=8765, electron_bin=tmp_path / "missing")
    assert ok is False and "no electron binary" in msg   # bails BEFORE touching any login item


def _patch_launchctl(monkeypatch, plist, calls, *, port_free=True, load_rc=0, healthy=True):
    monkeypatch.setattr(cd, "desktop_plist_path", lambda: plist)
    monkeypatch.setattr(cd, "_disable_label", lambda label: calls.append(("disable", label)))
    monkeypatch.setattr(cd, "_reload_label", lambda label: calls.append(("reload", label)))
    monkeypatch.setattr(fa, "_launchctl", lambda *a, **k: _R(load_rc, "load failed" if load_rc else ""))
    monkeypatch.setattr(fa, "_kickstart", lambda *a, **k: None)
    monkeypatch.setattr(fa, "wait_port_free", lambda *a, **k: port_free)
    monkeypatch.setattr(fa, "wait_port_busy", lambda *a, **k: True)
    monkeypatch.setattr(fa, "health_ok", lambda *a, **k: healthy)
    monkeypatch.setattr(fa, "remove_watchdog", lambda *a, **k: calls.append(("remove_watchdog",)) or True)
    monkeypatch.setattr(fa, "install_watchdog", lambda *a, **k: calls.append(("install_watchdog",)) or True)


def test_migrate_success_disables_fastapi_and_removes_its_watchdog(tmp_path, monkeypatch):
    elec = tmp_path / "electron"
    elec.write_text("")
    plist = tmp_path / "com.smbos.desktop.plist"
    calls = []
    _patch_launchctl(monkeypatch, plist, calls)
    ok, msg = cd.migrate(tmp_path, port=8765, electron_bin=elec)
    assert ok is True and "cut over" in msg
    assert plistlib.loads(plist.read_bytes())["Label"] == "com.smbos.desktop"
    assert ("disable", "com.smbos.dashboard") in calls   # FastAPI persistently disabled (won't RunAtLoad)
    assert ("disable", "com.smbos.tray") in calls         # the redundant Python tray too
    assert ("remove_watchdog",) in calls                  # so the FastAPI cron can't resurrect it
    assert ("install_watchdog",) not in calls             # not restored on a SUCCESSFUL flip


def test_migrate_rolls_back_when_unhealthy(tmp_path, monkeypatch):
    elec = tmp_path / "electron"
    elec.write_text("")
    plist = tmp_path / "com.smbos.desktop.plist"
    calls = []
    _patch_launchctl(monkeypatch, plist, calls, healthy=False)  # broker never answered
    ok, msg = cd.migrate(tmp_path, port=8765, electron_bin=elec)
    assert ok is False and "rolled back" in msg
    assert not plist.exists()                            # rollback removed the desktop agent
    assert ("reload", "com.smbos.dashboard") in calls    # FastAPI re-enabled
    assert ("install_watchdog",) in calls                # and its keep-alive cron restored


def test_migrate_rolls_back_when_port_never_frees(tmp_path, monkeypatch):
    elec = tmp_path / "electron"
    elec.write_text("")
    plist = tmp_path / "com.smbos.desktop.plist"
    _patch_launchctl(monkeypatch, plist, [], port_free=False)  # FastAPI never let go of the port
    ok, msg = cd.migrate(tmp_path, port=8765, electron_bin=elec)
    assert ok is False and "never freed" in msg and "rolled back" in msg


def test_main_requires_a_command():
    try:
        cd.main([])
    except SystemExit as e:
        assert "usage:" in str(e.code)
    else:
        raise AssertionError("main([]) should SystemExit with usage")
