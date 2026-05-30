"""Tests for /api/games."""

import json
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from iam_webserver.api.games import register


def _app(games_dir: Path) -> web.Application:
    app = web.Application()
    register(app, games_dir=games_dir)
    return app


async def test_missing_manifest_yields_empty_list(tmp_path: Path) -> None:
    async with TestClient(TestServer(_app(tmp_path))) as client:
        response = await client.get("/api/games")
        assert response.status == 200
        assert await response.json() == {"games": []}


async def test_manifest_is_surfaced(tmp_path: Path) -> None:
    manifest = {
        "games": [
            {
                "id": "stapzone",
                "name": "Stapzone Training",
                "entry": "index.html",
                "version": "1.0.0",
            }
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    async with TestClient(TestServer(_app(tmp_path))) as client:
        response = await client.get("/api/games")
        assert await response.json() == manifest


async def test_malformed_manifest_yields_empty_list(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("not json")
    async with TestClient(TestServer(_app(tmp_path))) as client:
        response = await client.get("/api/games")
        assert response.status == 200
        assert await response.json() == {"games": []}


async def test_manifest_missing_games_key_yields_empty_list(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"unrelated": 1}))
    async with TestClient(TestServer(_app(tmp_path))) as client:
        response = await client.get("/api/games")
        assert await response.json() == {"games": []}
