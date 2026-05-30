"""Tests for the calibration preset routes."""

import json
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from iam_webserver.api.calibration import register

_SQUARE_CORNERS = [[0.0, 0.0], [1000.0, 0.0], [1000.0, 1000.0], [0.0, 1000.0]]
_UNIT_SQUARE = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]


def _preset(name: str = "default") -> dict:
    return {
        "name": name,
        "source_corners": _SQUARE_CORNERS,
        "dest_corners": _UNIT_SQUARE,
    }


def _store(tmp_path: Path) -> tuple[Path, Path]:
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    return presets_dir, tmp_path / "active.json"


def _app(presets_dir: Path, active: Path) -> web.Application:
    app = web.Application()
    register(app, presets_dir=presets_dir, active_pointer_path=active)
    return app


@pytest.fixture
def store(tmp_path):
    return _store(tmp_path)


async def test_get_presets_empty_list(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        response = await client.get("/api/calibration/presets")
        assert response.status == 200
        data = await response.json()
        assert data == {"presets": [], "active": ""}


async def test_post_preset_writes_file(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        response = await client.post(
            "/api/calibration/presets", json=_preset("default")
        )
        assert response.status == 201
        payload = await response.json()
        assert payload["name"] == "default"

        on_disk = json.loads((presets_dir / "default.json").read_text())
        assert on_disk == _preset("default")


async def test_get_lists_written_presets(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        await client.post("/api/calibration/presets", json=_preset("a"))
        await client.post("/api/calibration/presets", json=_preset("b"))
        response = await client.get("/api/calibration/presets")
        data = await response.json()
        assert sorted(p["name"] for p in data["presets"]) == ["a", "b"]


async def test_get_one_preset(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        await client.post("/api/calibration/presets", json=_preset("rig-a"))
        response = await client.get("/api/calibration/presets/rig-a")
        assert response.status == 200
        data = await response.json()
        assert data == _preset("rig-a")


async def test_get_one_preset_missing_is_404(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        response = await client.get("/api/calibration/presets/ghost")
        assert response.status == 404


async def test_delete_preset_removes_file(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        await client.post("/api/calibration/presets", json=_preset("a"))
        assert (presets_dir / "a.json").exists()
        response = await client.delete("/api/calibration/presets/a")
        assert response.status == 204
        assert not (presets_dir / "a.json").exists()


async def test_delete_missing_preset_is_404(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        response = await client.delete("/api/calibration/presets/ghost")
        assert response.status == 404


async def test_post_active_pointer_writes_atomic_file(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        await client.post("/api/calibration/presets", json=_preset("rig-a"))
        response = await client.post(
            "/api/calibration/active", json={"name": "rig-a"}
        )
        assert response.status == 200
        payload = await response.json()
        assert payload == {"active": "rig-a"}
        assert json.loads(active.read_text()) == {"name": "rig-a"}


async def test_post_active_for_unknown_preset_is_404(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        response = await client.post(
            "/api/calibration/active", json={"name": "ghost"}
        )
        assert response.status == 404
        assert not active.exists()


async def test_get_active_pointer(store) -> None:
    presets_dir, active = store
    active.write_text(json.dumps({"name": "rig-a"}))
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        response = await client.get("/api/calibration/active")
        assert response.status == 200
        assert await response.json() == {"active": "rig-a"}


async def test_get_active_pointer_missing_is_empty(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        response = await client.get("/api/calibration/active")
        assert response.status == 200
        assert await response.json() == {"active": ""}


async def test_post_preset_rejects_missing_fields(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        bad = {"name": "x"}  # no corners
        response = await client.post("/api/calibration/presets", json=bad)
        assert response.status == 400


async def test_post_preset_rejects_wrong_corner_count(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        bad = {
            "name": "x",
            "source_corners": [[0, 0], [1, 0], [1, 1]],  # only 3
            "dest_corners": _UNIT_SQUARE,
        }
        response = await client.post("/api/calibration/presets", json=bad)
        assert response.status == 400


async def test_post_preset_rejects_invalid_name(store) -> None:
    """Names must be safe filesystem identifiers — no slashes or dots."""
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        for bad_name in ("", "..", "a/b", "a/../b"):
            response = await client.post(
                "/api/calibration/presets", json=_preset(bad_name)
            )
            assert response.status == 400, f"accepted invalid name {bad_name!r}"


async def test_post_preset_rejects_non_json_body(store) -> None:
    presets_dir, active = store
    async with TestClient(TestServer(_app(presets_dir, active))) as client:
        response = await client.post(
            "/api/calibration/presets",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 400
