"""Tests for the calibration-capture session routes.

The launcher walks the operator through the four projection-surface
corners; for each corner it asks the web-server to record the current
raw mm position of the active touch. The session accumulates these into
an in-memory buffer the launcher then posts as a preset.
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from iam_webserver.api.capture import register


class _Cache:
    """A LidarFrameCache stub exposing only what the capture handler reads."""

    def __init__(self, latest: dict | None = None) -> None:
        self.latest = latest


def _touch(*, raw_x_mm: float, raw_y_mm: float, x: float = 0.5, y: float = 0.5) -> dict:
    return {"id": 1, "x": x, "y": y, "raw_x_mm": raw_x_mm, "raw_y_mm": raw_y_mm}


def _frame(*touches: dict) -> dict:
    return {"seq": 1, "count": len(touches), "touches": list(touches)}


def _app(cache: _Cache) -> web.Application:
    app = web.Application()
    register(app, cache=cache)
    return app


@pytest.fixture
def cache():
    return _Cache()


async def test_get_session_starts_empty(cache) -> None:
    async with TestClient(TestServer(_app(cache))) as client:
        response = await client.get("/api/calibration/capture")
        assert response.status == 200
        data = await response.json()
        assert data == {"captured": {}}


async def test_capture_records_the_active_touch_raw_position(cache) -> None:
    cache.latest = _frame(_touch(raw_x_mm=120.0, raw_y_mm=240.0))
    async with TestClient(TestServer(_app(cache))) as client:
        response = await client.post(
            "/api/calibration/capture", json={"corner": "tl"}
        )
        assert response.status == 200
        data = await response.json()
        assert data["captured"]["tl"] == [120.0, 240.0]


async def test_capture_all_four_corners(cache) -> None:
    async with TestClient(TestServer(_app(cache))) as client:
        for corner, (mx, my) in zip(
            ("tl", "tr", "br", "bl"),
            ((0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)),
        ):
            cache.latest = _frame(_touch(raw_x_mm=mx, raw_y_mm=my))
            response = await client.post(
                "/api/calibration/capture", json={"corner": corner}
            )
            assert response.status == 200
        response = await client.get("/api/calibration/capture")
        assert (await response.json())["captured"] == {
            "tl": [0.0, 0.0],
            "tr": [1000.0, 0.0],
            "br": [1000.0, 1000.0],
            "bl": [0.0, 1000.0],
        }


async def test_capture_with_no_touch_active_is_409(cache) -> None:
    cache.latest = _frame()  # count: 0, no touch to read
    async with TestClient(TestServer(_app(cache))) as client:
        response = await client.post(
            "/api/calibration/capture", json={"corner": "tl"}
        )
        assert response.status == 409


async def test_capture_with_no_upstream_frame_is_409(cache) -> None:
    cache.latest = None
    async with TestClient(TestServer(_app(cache))) as client:
        response = await client.post(
            "/api/calibration/capture", json={"corner": "tl"}
        )
        assert response.status == 409


async def test_capture_invalid_corner_is_400(cache) -> None:
    cache.latest = _frame(_touch(raw_x_mm=1.0, raw_y_mm=2.0))
    async with TestClient(TestServer(_app(cache))) as client:
        for body in ({}, {"corner": "center"}, {"corner": ""}, "not a dict"):
            response = await client.post(
                "/api/calibration/capture", json=body
            )
            assert response.status == 400, f"accepted body {body!r}"


async def test_delete_resets_the_capture_session(cache) -> None:
    cache.latest = _frame(_touch(raw_x_mm=1.0, raw_y_mm=2.0))
    async with TestClient(TestServer(_app(cache))) as client:
        await client.post("/api/calibration/capture", json={"corner": "tl"})
        response = await client.delete("/api/calibration/capture")
        assert response.status == 204
        response = await client.get("/api/calibration/capture")
        assert (await response.json())["captured"] == {}
