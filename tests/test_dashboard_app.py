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


def test_plate_requires_token(tmp_path):
    app = dashboard_app.create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/plate").status_code == 401          # missing token
        assert client.get("/api/plate", params={"t": "wrong"}).status_code == 401  # bad token


def test_plate_returns_tasks_in_priority_order(tmp_path):
    ss.record_task(tmp_path, "ops", "review", "alpha", priority=5)
    ss.record_task(tmp_path, "ops", "review", "beta", priority=1)
    app = dashboard_app.create_app(tmp_path)
    token = lib.dashboard_token(tmp_path)
    with TestClient(app) as client:
        r = client.get("/api/plate", params={"t": token})
    assert r.status_code == 200
    assert [t["subject"] for t in r.json()["plate"]] == ["alpha", "beta"]


def test_events_requires_token(tmp_path):
    app = dashboard_app.create_app(tmp_path)
    with TestClient(app) as client:
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
    assert len(events) == 1 and events[0].startswith("event: plate\n")
