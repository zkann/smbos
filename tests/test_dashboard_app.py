"""Tests for the FastAPI live-mirror app. Skipped where fastapi/httpx aren't installed
(the stdlib CI job); the app CI job installs requirements-dev and runs them."""
import asyncio

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

import dashboard_app  # noqa: E402
import smbos_lib as lib  # noqa: E402
import state_store as ss  # noqa: E402


class _FakeRequest:
    """Stand-in for a Starlette Request whose client disconnects after the first event."""
    async def is_disconnected(self):
        return True


def test_positive_env_clamps_non_positive_and_garbage(monkeypatch):
    # a <=0 or non-numeric poll/heartbeat would busy-spin the SSE loop -> falls back to default
    for bad in ("0", "-3", "abc", "", "inf", "-inf", "nan"):  # inf would hang asyncio.sleep forever
        monkeypatch.setenv("X_SSE", bad)
        assert dashboard_app._positive_env("X_SSE", "1.0") == 1.0
    monkeypatch.setenv("X_SSE", "0.05")
    assert dashboard_app._positive_env("X_SSE", "1.0") == 0.05
    monkeypatch.delenv("X_SSE", raising=False)
    assert dashboard_app._positive_env("X_SSE", "2.5") == 2.5


def _fixture_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>x</title></head>"
        "<body><div id=app></div></body></html>", encoding="utf-8")
    (dist / "assets" / "index.js").write_text("console.log('spa')", encoding="utf-8")
    return dist


def test_index_requires_token(tmp_path):
    app = dashboard_app.create_app(tmp_path, dist_dir=_fixture_dist(tmp_path))
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/").status_code == 401


def test_index_no_token_serves_friendly_html(tmp_path):
    # no token AND a wrong token both get the friendly styled page, never the real SPA
    app = dashboard_app.create_app(tmp_path, dist_dir=_fixture_dist(tmp_path))
    with TestClient(app, base_url="http://localhost") as client:
        for url in ("/", "/?t=garbage"):
            r = client.get(url)
            assert r.status_code == 401 and "text/html" in r.headers["content-type"]
            assert "access token" in r.text and "SmbOS" in r.text
            assert "__SMBOS_TOKEN__" not in r.text  # the token-injected SPA is NOT served
            assert r.headers.get("referrer-policy") == "no-referrer"
            assert "no-store" in r.headers.get("cache-control", "")


def test_index_serves_spa_with_injected_token(tmp_path):
    app = dashboard_app.create_app(tmp_path, dist_dir=_fixture_dist(tmp_path))
    token = lib.dashboard_token(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        r = client.get("/", params={"t": token})
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert f'window.__SMBOS_TOKEN__="{token}"' in r.text  # token injected for the SPA
        asset = client.get("/assets/index.js")
        assert asset.status_code == 200 and "spa" in asset.text  # bundle served (no secrets)


def test_assets_404_before_build_then_served_after(tmp_path):
    # server started BEFORE the SPA is built (no dist/assets): /assets is a clean 404, NOT a
    # 500, and once a later build produces the bundle it's served with no restart.
    dist = tmp_path / "dist"
    dist.mkdir()  # no assets/ yet
    app = dashboard_app.create_app(tmp_path, dist_dir=dist)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/assets/index.js").status_code == 404  # pre-build: clean 404, no crash
        (dist / "assets").mkdir()
        (dist / "assets" / "index.js").write_text("late", encoding="utf-8")
        r = client.get("/assets/index.js")
        assert r.status_code == 200 and "late" in r.text  # late build served, no restart
        assert client.get("/assets/missing.js").status_code == 404  # missing file -> 404


def test_assets_rejects_path_traversal(tmp_path):
    app = dashboard_app.create_app(tmp_path, dist_dir=_fixture_dist(tmp_path))
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")
    with TestClient(app, base_url="http://localhost") as client:
        # escape attempts resolve outside dist/assets -> 404, never serve the secret
        for evil in ("../../secret.txt", "..%2f..%2fsecret.txt", "....//secret.txt"):
            r = client.get(f"/assets/{evil}")
            assert r.status_code == 404 and "SECRET" not in r.text


def test_index_500_when_no_head_anchor(tmp_path):
    # a built-but-anchorless page must fail loud, not serve a tokenless (blank) dashboard
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>no head here</body></html>", encoding="utf-8")
    app = dashboard_app.create_app(tmp_path, dist_dir=dist)
    token = lib.dashboard_token(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        r = client.get("/", params={"t": token})
        assert r.status_code == 500 and "head" in r.text.lower()


def test_index_sets_no_referrer_and_no_store(tmp_path):
    # the injected page carries the secret: don't cache it, don't leak ?t= via Referer
    app = dashboard_app.create_app(tmp_path, dist_dir=_fixture_dist(tmp_path))
    token = lib.dashboard_token(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        r = client.get("/", params={"t": token})
        assert r.headers.get("referrer-policy") == "no-referrer"
        assert "no-store" in r.headers.get("cache-control", "")


def test_index_503_when_spa_not_built(tmp_path):
    app = dashboard_app.create_app(tmp_path, dist_dir=tmp_path / "nope")
    token = lib.dashboard_token(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        r = client.get("/", params={"t": token})
        assert r.status_code == 503 and "not built" in r.text


def test_plate_requires_token(tmp_path):
    app = dashboard_app.create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/plate").status_code == 401          # missing token
        assert client.get("/api/plate", params={"t": "wrong"}).status_code == 401  # bad token


def test_plate_returns_tasks_in_priority_order(tmp_path):
    ss.record_task(tmp_path, "ops", "review", "alpha", priority=5)
    ss.record_task(tmp_path, "ops", "review", "beta", priority=1)
    app = dashboard_app.create_app(tmp_path)
    token = lib.dashboard_token(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        r = client.get("/api/plate", params={"t": token})
    assert r.status_code == 200
    assert [t["subject"] for t in r.json()["plate"]] == ["alpha", "beta"]


def test_events_requires_token(tmp_path):
    app = dashboard_app.create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/events").status_code == 401


def test_events_emits_initial_plate_snapshot(tmp_path):
    # drive the SSE generator directly (no HTTP streaming, which would hang an infinite gen
    # under TestClient). The first yield must be a plate snapshot, emitted before any poll.
    ss.record_task(tmp_path, "ops", "review", "stream-me")

    async def first_event():
        gen = dashboard_app.event_stream(tmp_path, _FakeRequest())
        try:
            return await gen.__anext__()
        finally:
            await gen.aclose()

    out = asyncio.run(first_event())
    assert out.startswith("event: plate\n") and "stream-me" in out


def test_events_generator_stops_on_disconnect(tmp_path):
    # after the initial snapshot, a disconnected client ends the stream (no infinite loop)
    async def drain():
        gen = dashboard_app.event_stream(tmp_path, _FakeRequest())
        events = [e async for e in gen]  # _FakeRequest is always disconnected -> ends after snapshot
        return events

    events = asyncio.run(asyncio.wait_for(drain(), timeout=5))
    # initial snapshot is two frames (plate + runs), then the disconnected client ends it
    assert len(events) == 2
    assert events[0].startswith("event: plate\n") and events[1].startswith("event: runs\n")


def test_runs_requires_token(tmp_path):
    app = dashboard_app.create_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/runs").status_code == 401


def test_runs_returns_recorded_runs(tmp_path):
    rid = ss.start_run(tmp_path, "weekly-report", surface="cron")
    ss.finish_run(tmp_path, rid, result="ok", cost_usd=0.5)
    app = dashboard_app.create_app(tmp_path)
    token = lib.dashboard_token(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        r = client.get("/api/runs", params={"t": token})
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert len(runs) == 1 and runs[0]["sop_id"] == "weekly-report" and runs[0]["result"] == "ok"


def test_events_initial_snapshot_includes_runs(tmp_path):
    rid = ss.start_run(tmp_path, "weekly-report", surface="cron")
    ss.finish_run(tmp_path, rid, result="ok")

    async def first_two():
        gen = dashboard_app.event_stream(tmp_path, _FakeRequest())
        out = [await gen.__anext__(), await gen.__anext__()]
        await gen.aclose()
        return out

    plate_frame, runs_frame = asyncio.run(first_two())
    assert plate_frame.startswith("event: plate\n")
    assert runs_frame.startswith("event: runs\n") and "weekly-report" in runs_frame


class _ConnectedFor:
    """Disconnects after `n` polls, so the streaming loop actually runs."""
    def __init__(self, n):
        self.n = n

    async def is_disconnected(self):
        self.n -= 1
        return self.n < 0


def test_events_emits_new_plate_after_db_change(tmp_path, monkeypatch):
    # the held-connection data_version premise: a write from ANOTHER connection mid-stream
    # is detected and pushed as a fresh plate. This is the loop body nothing else covers.
    monkeypatch.setattr(dashboard_app, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(dashboard_app, "HEARTBEAT_SECONDS", 1000.0)  # keep heartbeat out of the way

    async def run():
        gen = dashboard_app.event_stream(tmp_path, _ConnectedFor(20))
        events = [await gen.__anext__()]            # initial plate frame
        ss.record_task(tmp_path, "ops", "review", "appeared")  # separate connection commits
        seen_appeared = False
        try:
            async for e in gen:
                events.append(e)
                if "appeared" in e:
                    seen_appeared = True
                elif seen_appeared and e.startswith("event: runs\n"):
                    break  # the runs frame paired with the on-change plate frame
        finally:
            await gen.aclose()
        return events

    events = asyncio.run(asyncio.wait_for(run(), timeout=5))
    assert events[0].startswith("event: plate")
    assert any("appeared" in e and e.startswith("event: plate\n") for e in events)  # change detected
    assert events[-1].startswith("event: runs\n")  # on-change emit pushes a runs frame too


def test_events_emits_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(dashboard_app, "HEARTBEAT_SECONDS", 0.02)  # ~2 polls

    async def run():
        gen = dashboard_app.event_stream(tmp_path, _ConnectedFor(50))
        events = []
        try:
            async for e in gen:
                events.append(e)
                if "event: heartbeat" in e:
                    break
        finally:
            await gen.aclose()
        return events

    events = asyncio.run(asyncio.wait_for(run(), timeout=5))
    assert any("event: heartbeat" in e for e in events)


def test_cors_allows_only_the_legacy_origin(tmp_path):
    # the legacy dashboard page (its loopback origin) may consume the stream cross-origin;
    # any other origin gets no Access-Control-Allow-Origin (browser blocks the read)
    app = dashboard_app.create_app(tmp_path)
    token = lib.dashboard_token(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        legacy = client.get("/api/plate", params={"t": token},
                            headers={"Origin": "http://127.0.0.1:8765"})
        assert legacy.headers.get("access-control-allow-origin") == "http://127.0.0.1:8765"
        evil = client.get("/api/plate", params={"t": token},
                          headers={"Origin": "http://evil.example.com"})
        assert evil.headers.get("access-control-allow-origin") is None


def test_rejects_non_loopback_host(tmp_path):
    # DNS-rebinding defense: a non-loopback Host is 403'd even with a valid token
    ss.record_task(tmp_path, "ops", "review", "secret-ish")
    app = dashboard_app.create_app(tmp_path)
    token = lib.dashboard_token(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        bad = client.get("/api/plate", params={"t": token}, headers={"host": "evil.example.com"})
        assert bad.status_code == 403
        good = client.get("/api/plate", params={"t": token}, headers={"host": "127.0.0.1:8766"})
        assert good.status_code == 200
