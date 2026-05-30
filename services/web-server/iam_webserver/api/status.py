"""GET /api/status — combined lidar-service and stream-freshness view.

Merges the JSON document lidar-service writes (atomic state snapshot) with
the web-server's live observation of the frame socket. The launcher's
status view and any callers that need a fresh-data check call this.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from aiohttp import web

_log = logging.getLogger(__name__)


class _LidarStreamView(Protocol):
    connected: bool
    last_frame_ts: float | None


_DEFAULT_LIDAR: dict = {
    "state": "unknown",
    "has_baseline": False,
    "last_seq": 0,
    "last_seen_ts": 0.0,
    "active_preset": "",
    "status_updated_at": None,
}
_FILE_KEYS = ("state", "has_baseline", "last_seq", "last_seen_ts", "active_preset")


def build_status(status_file: Path | str, cache: _LidarStreamView) -> dict:
    """Build the /api/status response document.

    Reads ``status_file`` (the JSON lidar-service writes) and overlays the
    web-server's live observation of the frame socket. A missing or
    malformed file is tolerated — the returned document degrades to
    ``state: "unknown"`` rather than raising.
    """
    lidar = dict(_DEFAULT_LIDAR)
    lidar["stream_connected"] = cache.connected
    lidar["stream_last_frame_ts"] = cache.last_frame_ts

    path = Path(status_file)
    try:
        raw = path.read_text()
    except (FileNotFoundError, OSError):
        return {"lidar": lidar}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log.warning("status file %s is not valid JSON: %s", path, exc)
        return {"lidar": lidar}

    if not isinstance(data, dict):
        _log.warning("status file %s is not a JSON object; ignoring", path)
        return {"lidar": lidar}

    for key in _FILE_KEYS:
        if key in data:
            lidar[key] = data[key]
    if "updated_at" in data:
        lidar["status_updated_at"] = data["updated_at"]
    return {"lidar": lidar}


def register(
    app: web.Application,
    *,
    status_file: Path | str,
    cache: _LidarStreamView,
) -> None:
    """Mount GET /api/status on ``app``."""

    async def handler(_request: web.Request) -> web.Response:
        return web.json_response(build_status(status_file, cache))

    app.router.add_get("/api/status", handler)
