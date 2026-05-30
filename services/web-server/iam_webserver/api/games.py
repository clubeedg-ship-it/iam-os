"""GET /api/games — read the games manifest the launcher displays.

Phase 5 populates the manifest with real games. For Phase 4 the endpoint
returns an empty list when the manifest is missing or malformed, so the
launcher's games view degrades cleanly until the manifest exists.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from aiohttp import web

_log = logging.getLogger(__name__)


def register(app: web.Application, *, games_dir: Path | str) -> None:
    """Mount GET /api/games on ``app``."""
    manifest_path = Path(games_dir) / "manifest.json"

    async def handler(_request: web.Request) -> web.Response:
        try:
            data = json.loads(manifest_path.read_text())
        except (FileNotFoundError, OSError):
            return web.json_response({"games": []})
        except json.JSONDecodeError as exc:
            _log.warning("games manifest at %s is invalid JSON: %s", manifest_path, exc)
            return web.json_response({"games": []})
        if not isinstance(data, dict) or not isinstance(data.get("games"), list):
            return web.json_response({"games": []})
        return web.json_response(data)

    app.router.add_get("/api/games", handler)
