"""Tests for the assembled aiohttp application: static + API routing."""

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from iam_webserver.app import create_app
from iam_webserver.config import (
    CalibrationConfig,
    Config,
    LidarConfig,
    LoggingConfig,
    PathsConfig,
    ServerConfig,
)


class _StubCache:
    def __init__(self) -> None:
        self.latest: dict | None = None
        self.connected = False
        self.last_frame_ts: float | None = None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


def _config(tmp_path: Path) -> Config:
    launcher_dist = tmp_path / "launcher-dist"
    launcher_dist.mkdir()
    (launcher_dist / "index.html").write_text(
        "<!doctype html><title>IAM-OS launcher</title>"
    )
    (launcher_dist / "assets").mkdir()
    (launcher_dist / "assets" / "main.js").write_text("// launcher entrypoint")

    games_dir = tmp_path / "games"
    games_dir.mkdir()

    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()

    return Config(
        server=ServerConfig(host="127.0.0.1", port=8080),
        paths=PathsConfig(
            launcher_dist=str(launcher_dist),
            games_dir=str(games_dir),
        ),
        lidar=LidarConfig(
            socket_path=str(tmp_path / "lidar.sock"),
            status_file=str(tmp_path / "lidar-status.json"),
            reconnect_initial_s=0.5,
            reconnect_max_s=5.0,
        ),
        calibration=CalibrationConfig(
            presets_dir=str(presets_dir),
            active_pointer_path=str(presets_dir / "active.json"),
        ),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.fixture
def cache():
    return _StubCache()


async def test_root_returns_launcher_index(tmp_path: Path, cache) -> None:
    app = create_app(_config(tmp_path), cache=cache)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/")
        assert response.status == 200
        body = await response.text()
        assert "IAM-OS launcher" in body


async def test_unknown_path_falls_back_to_index_for_spa_routes(
    tmp_path: Path, cache
) -> None:
    """Hash routing is on the SPA side; deep links still serve index.html."""
    app = create_app(_config(tmp_path), cache=cache)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/calibrate")
        assert response.status == 200
        body = await response.text()
        assert "IAM-OS launcher" in body


async def test_static_asset_is_served(tmp_path: Path, cache) -> None:
    app = create_app(_config(tmp_path), cache=cache)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/assets/main.js")
        assert response.status == 200
        assert await response.text() == "// launcher entrypoint"


async def test_games_static_dir_is_served(tmp_path: Path, cache) -> None:
    config = _config(tmp_path)
    games_dir = Path(config.paths.games_dir)
    (games_dir / "demo").mkdir()
    (games_dir / "demo" / "index.html").write_text("<title>demo game</title>")
    app = create_app(config, cache=cache)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/games/demo/index.html")
        assert response.status == 200
        assert "demo game" in await response.text()


async def test_api_status_is_registered(tmp_path: Path, cache) -> None:
    app = create_app(_config(tmp_path), cache=cache)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/status")
        assert response.status == 200
        data = await response.json()
        assert "lidar" in data


async def test_api_games_is_registered(tmp_path: Path, cache) -> None:
    config = _config(tmp_path)
    games_dir = Path(config.paths.games_dir)
    (games_dir / "manifest.json").write_text(
        json.dumps({"games": [{"id": "demo", "name": "Demo"}]})
    )
    app = create_app(config, cache=cache)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/games")
        data = await response.json()
        assert data["games"][0]["id"] == "demo"


async def test_api_calibration_preset_is_registered(tmp_path: Path, cache) -> None:
    app = create_app(_config(tmp_path), cache=cache)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/calibration/presets")
        assert response.status == 200


async def test_api_calibration_capture_is_registered(tmp_path: Path, cache) -> None:
    app = create_app(_config(tmp_path), cache=cache)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/calibration/capture")
        assert response.status == 200


async def test_api_route_is_not_shadowed_by_spa_fallback(
    tmp_path: Path, cache
) -> None:
    """The SPA fallback must not eat /api/* paths."""
    app = create_app(_config(tmp_path), cache=cache)
    async with TestClient(TestServer(app)) as client:
        # An unknown /api/* route must 404, not serve index.html.
        response = await client.get("/api/does-not-exist")
        assert response.status == 404


async def test_app_starts_and_stops_the_lidar_cache(tmp_path: Path) -> None:
    """create_app schedules cache.start() / cache.stop() as lifecycle hooks."""

    class _LifecycleCache(_StubCache):
        def __init__(self) -> None:
            super().__init__()
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    cache = _LifecycleCache()
    app = create_app(_config(tmp_path), cache=cache)
    async with TestClient(TestServer(app)):
        assert cache.started is True
    assert cache.stopped is True
