"""Assemble the aiohttp application: static + API + lifecycle.

Mounts the launcher SPA at ``/`` (unknown paths fall back to ``index.html``
so client-side hash routing works on deep links), the games tree at
``/games/``, and the JSON API under ``/api/``. Lifecycle hooks start the
lidar.sock cache when the app starts and stop it on shutdown.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from aiohttp import web

from iam_webserver.api import calibration as calibration_api
from iam_webserver.api import capture as capture_api
from iam_webserver.api import games as games_api
from iam_webserver.api import status as status_api
from iam_webserver.config import Config

_log = logging.getLogger(__name__)


class _LidarCache(Protocol):
    latest: dict | None
    connected: bool
    last_frame_ts: float | None

    async def start(self) -> None: ...
    async def stop(self) -> None: ...


def create_app(config: Config, *, cache: _LidarCache) -> web.Application:
    """Assemble the aiohttp application from ``config`` and the lidar cache."""
    app = web.Application()

    launcher_dist = Path(config.paths.launcher_dist)
    games_dir = Path(config.paths.games_dir)

    status_api.register(
        app,
        status_file=Path(config.lidar.status_file),
        cache=cache,
    )
    calibration_api.register(
        app,
        presets_dir=Path(config.calibration.presets_dir),
        active_pointer_path=Path(config.calibration.active_pointer_path),
    )
    capture_api.register(app, cache=cache)
    games_api.register(app, games_dir=games_dir)

    if games_dir.is_dir():
        app.router.add_static("/games/", str(games_dir), show_index=False)
    _mount_launcher(app, launcher_dist)

    async def _on_startup(_app: web.Application) -> None:
        await cache.start()

    async def _on_cleanup(_app: web.Application) -> None:
        await cache.stop()

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


def _mount_launcher(app: web.Application, launcher_dist: Path) -> None:
    """Serve the SPA: known files pass through, unknown paths get index.html.

    The launcher uses hash routing (e.g. ``#/calibrate``), so the server
    only ever serves ``index.html`` plus its referenced static assets.
    Any GET that does not match a known file falls back to ``index.html``
    so a refresh on a deep link still loads the SPA.
    """
    index_path = launcher_dist / "index.html"

    async def root(_request: web.Request) -> web.Response:
        return web.FileResponse(index_path)

    async def spa(request: web.Request) -> web.StreamResponse:
        path = request.match_info["path"]
        # The catchall must not shadow unregistered /api/* paths; without
        # this guard a typo URL would serve index.html with a 200 and any
        # client error-handling would silently fall through to the SPA.
        if path == "api" or path.startswith("api/"):
            raise web.HTTPNotFound()
        candidate = launcher_dist / path
        if candidate.is_file() and _is_within(candidate, launcher_dist):
            return web.FileResponse(candidate)
        return web.FileResponse(index_path)

    app.router.add_get("/", root)
    app.router.add_get("/{path:.+}", spa)


def _is_within(child: Path, parent: Path) -> bool:
    """True if ``child`` resolves inside ``parent`` — guards against ``..``."""
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True
