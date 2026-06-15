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
        events = [await gen.__anext__()]            # initial (empty) snapshot
        ss.record_task(tmp_path, "ops", "review", "appeared")  # separate connection commits
        try:
            async for e in gen:
                events.append(e)
                if "appeared" in e:
                    break
        finally:
            await gen.aclose()
        return events

    events = asyncio.run(asyncio.wait_for(run(), timeout=5))
    assert events[0].startswith("event: plate")
    assert any("appeared" in e for e in events[1:])  # change detected across connections


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
