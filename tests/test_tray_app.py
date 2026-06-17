"""Menu-bar tray: badge state model, menu IA/copy, fetch, and plist shape.

Stdlib-only (rumps is import-guarded in tray_app, so this runs in the plain `test` job on
3.9 and 3.12 without pyobjc). The network and launchctl are faked: we assert the pure view
logic and orchestration, the design-review decisions encoded as tests.
"""
import json
import plistlib
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import tray_app as tray  # noqa: E402


# --- badge state model (D2: icon-only at zero; count is the signal) -----------------------
def test_badge_loading_is_a_dot_not_a_zero():
    # Don't flash a wrong "0" before the first poll lands.
    assert tray.badge_title(None) == tray.GLYPH_LOADING


def test_badge_zero_waiting_is_neutral_glyph_no_number():
    # DESIGN.md:22 zero renders neutral, never tinted; no number at rest.
    assert tray.badge_title({"status": "ok", "waiting": 0, "inflight": 2, "coming": 1}) == tray.GLYPH_IDLE


def test_badge_counts_waiting_only():
    # The badge tracks the plate (what needs you), not in-flight/coming-up.
    assert tray.badge_title({"status": "ok", "waiting": 3, "inflight": 9, "coming": 9}) == "{} 3".format(tray.GLYPH_WORK)


def test_badge_down_is_warning_glyph():
    assert tray.badge_title({"status": "down"}) == tray.GLYPH_DOWN


# --- accessibility: spoken label, never number/color-only (Dim4) --------------------------
@pytest.mark.parametrize("state,expected", [
    (None, "SmbOS, loading"),
    ({"status": "down"}, "SmbOS, dashboard not running"),
    ({"status": "ok", "waiting": 0}, "SmbOS, nothing waiting for you"),
    ({"status": "ok", "waiting": 1}, "SmbOS, 1 waiting for you"),
])
def test_accessibility_label(state, expected):
    assert tray.accessibility_label(state) == expected


# --- menu IA + copy (Dim2/D3: breakdown, house voice, no jargon) --------------------------
def _titles(model):
    return [i["title"] for i in model if not i.get("sep")]


def test_menu_shows_three_bucket_breakdown():
    model = tray.menu_model({"status": "ok", "waiting": 3, "inflight": 1, "coming": 2})
    titles = _titles(model)
    assert "3 waiting for you" in titles
    assert "1 in flight" in titles
    assert "2 coming up" in titles


def test_menu_hides_empty_buckets_but_keeps_nonzero():
    # waiting==0 with work elsewhere: no "waiting" line, but in-flight still shows.
    titles = _titles(tray.menu_model({"status": "ok", "waiting": 0, "inflight": 1, "coming": 0}))
    assert "1 in flight" in titles
    assert not any("waiting for you" in t for t in titles if t != "SmbOS")


def test_menu_all_zero_uses_dashboard_empty_copy():
    titles = _titles(tray.menu_model({"status": "ok", "waiting": 0, "inflight": 0, "coming": 0}))
    assert "Nothing waiting for you right now." in titles


def test_menu_kills_daemon_jargon():
    # "Restart dashboard", never "Restart daemon" (DESIGN.md owner-facing voice).
    all_titles = " | ".join(_titles(tray.menu_model({"status": "ok", "waiting": 1})))
    assert "daemon" not in all_titles.lower()
    assert "Restart dashboard" in all_titles


def test_menu_down_state_copy_and_fix():
    model = tray.menu_model({"status": "down"})
    titles = _titles(model)
    assert "Dashboard isn't running" in titles  # what happened
    assert "Start it" in titles                 # the one fix
    # the down menu is minimal: no breakdown, no "Open dashboard"
    assert not any("waiting for you" in t for t in titles)
    assert "Open dashboard" not in titles


def test_menu_has_no_panel_controls_without_an_app():
    # Pure-logic callers omit panel_mode; no panel controls leak in (back-compat).
    titles = _titles(tray.menu_model({"status": "ok", "waiting": 1}))
    assert not any(t in ("Show panel", "Hide panel", "Dock as sidebar", "Undock panel")
                   for t in titles)


def test_menu_panel_controls_per_mode():
    peek = _titles(tray.menu_model({"status": "ok", "waiting": 1}, panel_mode=tray.MODE_PEEK))
    assert "Dock as sidebar" in peek and "Hide panel" in peek
    docked = _titles(tray.menu_model({"status": "ok", "waiting": 1}, panel_mode=tray.MODE_DOCKED))
    assert "Undock panel" in docked and "Hide panel" in docked
    hidden = _titles(tray.menu_model({"status": "ok", "waiting": 1}, panel_mode=tray.MODE_HIDDEN))
    assert hidden.count("Show panel") == 1 and "Dock as sidebar" not in hidden


def test_menu_panel_controls_present_even_when_down():
    titles = _titles(tray.menu_model({"status": "down"}, panel_mode=tray.MODE_PEEK))
    assert "Dock as sidebar" in titles and "Hide panel" in titles


# --- panel geometry, peek triggers, and window-fit (pure) --------------------------------
def test_panel_and_handle_rects_hug_right_edge():
    # screen 100..1700 (w=1600), panel width 360 -> panel x = 100+1600-360 = 1340
    assert tray.panel_rect(100, 0, 1600, 1000, width=360) == (1340, 0, 360, 1000)
    assert tray.handle_rect(100, 0, 1600, 1000, width=6) == (1694, 0, 6, 1000)


def test_peek_show_at_edge_hide_past_panel():
    vx, vw = 0, 1600
    assert tray.peek_should_show(1599, vx, vw, edge_px=2) is True   # cursor at the edge
    assert tray.peek_should_show(1500, vx, vw, edge_px=2) is False  # not yet
    # open drawer hides only once cursor is left of the panel minus hysteresis
    assert tray.peek_should_hide(1200, vx, vw, width=360, hysteresis=12) is True
    assert tray.peek_should_hide(1235, vx, vw, width=360, hysteresis=12) is False


def test_fit_width_shrinks_overlap_else_none():
    # window 0..1500 on a 1600 screen, panel 360 -> limit_right=1240, overlaps -> shrink to 1240
    assert tray.fit_width(0, 1500, 0, 1600, panel_width=360) == 1240
    # window already left of the panel: no change
    assert tray.fit_width(0, 1000, 0, 1600, panel_width=360) is None
    # never below the floor
    assert tray.fit_width(1300, 300, 0, 1600, panel_width=360, min_width=320) == 320


def test_menu_identity_first_and_info_rows_disabled():
    model = tray.menu_model({"status": "ok", "waiting": 2})
    assert model[0]["title"] == "SmbOS" and model[0]["enabled"] is False
    # the identity header carries no action
    assert model[0]["action"] is None


# --- fetch: counts on success, None (disconnected) on any failure -------------------------
class _Resp:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._payload


def _fake_opener(mapping):
    def opener(url, timeout=2):
        for needle, payload in mapping.items():
            if needle in url:
                return _Resp(payload)
        raise AssertionError("unexpected url: {}".format(url))
    return opener


def test_fetch_counts_reads_three_buckets(tmp_path):
    # Point _server at a recorded daemon (actual port/token), then fake the HTTP.
    (tmp_path / tray.SERVER_FILE).write_text(json.dumps({"port": 9999, "token": "tok"}))
    opener = _fake_opener({
        "/api/plate": {"plate": [1, 2, 3]},
        "/api/inflight": {"inflight": [1]},
        "/api/queue": {"queue": [1, 2]},
    })
    assert tray.fetch_counts(tmp_path, opener) == {"waiting": 3, "inflight": 1, "coming": 2}


def test_fetch_counts_returns_none_when_daemon_down(tmp_path):
    (tmp_path / tray.SERVER_FILE).write_text(json.dumps({"port": 9999, "token": "tok"}))

    def down(url, timeout=2):
        raise urllib.error.URLError("connection refused")

    assert tray.fetch_counts(tmp_path, down) is None  # the disconnected signal


def test_compute_state_maps_none_to_down():
    assert tray.compute_state(None) == {"status": "down"}
    assert tray.compute_state({"waiting": 1, "inflight": 0, "coming": 0})["status"] == "ok"


# --- launchd plist: distinct label, runs the venv python, starts at login -----------------
def test_tray_plist_shape():
    d = plistlib.loads(tray.tray_plist_xml(
        "/tmp/sops", "/Apps/SmbOS.app/Contents/MacOS/SmbOS", "/venv/site-packages").encode("utf-8"))
    assert d["Label"] == tray.TRAY_LABEL
    assert d["Label"] != tray.daemon.AGENT_LABEL  # never collides with the daemon's job
    args = d["ProgramArguments"]
    assert args[0] == "/Apps/SmbOS.app/Contents/MacOS/SmbOS"  # launched via the named bundle
    assert str(tray.APP) in args                  # symlinked interpreter needs the script
    assert args[args.index("--sop-dir") + 1] == "/tmp/sops"
    assert d["EnvironmentVariables"]["PYTHONPATH"] == "/venv/site-packages"  # deps for the symlink
    assert d["RunAtLoad"] is True                  # login durability


def test_tray_plist_defaults_to_bundle_exec():
    d = plistlib.loads(tray.tray_plist_xml("/tmp/sops").encode("utf-8"))
    assert d["ProgramArguments"][0] == str(tray.bundle_exec())  # the .app, not bare python
    assert "SmbOS.app" in d["ProgramArguments"][0]


def test_build_app_bundle_writes_named_plist_and_exec(tmp_path):
    bundle = tmp_path / "SmbOS.app"
    fake_python = tmp_path / "python"
    fake_python.write_text("#!/bin/sh\n")
    exe = tray.build_app_bundle(python_exec=fake_python, bundle=bundle)
    info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleName"] == "SmbOS"          # the name macOS shows in notifications
    assert info["CFBundleIdentifier"] == tray.TRAY_LABEL
    assert info["LSUIElement"] is True
    assert exe.is_symlink() and exe.resolve() == fake_python.resolve()  # exec IS the interpreter
