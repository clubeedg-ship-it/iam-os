"""Tests for /api/status.

The launcher's status view reads this endpoint. It combines two sources
of truth: the JSON file lidar-service writes (state, has_baseline,
last_seq, last_seen_ts, active_preset, updated_at) and the web-server's
own live observation of the frame socket (stream_connected,
stream_last_frame_ts).
"""

import json
import time
from pathlib import Path

from iam_webserver.api.status import build_status


class _Cache:
    """A stand-in for LidarFrameCache that exposes only what build_status reads."""

    def __init__(
        self, *, connected: bool = False, last_frame_ts: float | None = None
    ) -> None:
        self.connected = connected
        self.last_frame_ts = last_frame_ts


def test_missing_status_file_yields_unknown_state(tmp_path: Path) -> None:
    payload = build_status(tmp_path / "missing.json", _Cache())
    assert payload["lidar"]["state"] == "unknown"
    assert payload["lidar"]["has_baseline"] is False
    assert payload["lidar"]["active_preset"] == ""
    assert payload["lidar"]["stream_connected"] is False
    assert payload["lidar"]["stream_last_frame_ts"] is None
    assert payload["lidar"]["status_updated_at"] is None


def test_status_file_fields_are_surfaced(tmp_path: Path) -> None:
    target = tmp_path / "lidar-status.json"
    target.write_text(
        json.dumps(
            {
                "state": "streaming",
                "last_seq": 42,
                "last_seen_ts": 100.5,
                "has_baseline": True,
                "active_preset": "default",
                "updated_at": 101.0,
            }
        )
    )
    payload = build_status(target, _Cache(connected=True, last_frame_ts=101.5))
    lidar = payload["lidar"]
    assert lidar["state"] == "streaming"
    assert lidar["last_seq"] == 42
    assert lidar["last_seen_ts"] == 100.5
    assert lidar["has_baseline"] is True
    assert lidar["active_preset"] == "default"
    assert lidar["status_updated_at"] == 101.0
    assert lidar["stream_connected"] is True
    assert lidar["stream_last_frame_ts"] == 101.5


def test_malformed_status_file_is_tolerated(tmp_path: Path) -> None:
    target = tmp_path / "lidar-status.json"
    target.write_text("not json")
    payload = build_status(target, _Cache())
    assert payload["lidar"]["state"] == "unknown"


def test_status_file_without_a_known_key_falls_back_to_defaults(
    tmp_path: Path,
) -> None:
    target = tmp_path / "lidar-status.json"
    target.write_text(json.dumps({"state": "stale"}))
    payload = build_status(target, _Cache())
    assert payload["lidar"]["state"] == "stale"
    assert payload["lidar"]["last_seq"] == 0
    assert payload["lidar"]["active_preset"] == ""


def test_status_file_that_is_not_a_dict_is_tolerated(tmp_path: Path) -> None:
    target = tmp_path / "lidar-status.json"
    target.write_text(json.dumps(["not", "an", "object"]))
    payload = build_status(target, _Cache())
    assert payload["lidar"]["state"] == "unknown"


async def test_handler_returns_json_over_http(tmp_path: Path) -> None:
    """The aiohttp handler delivers build_status as JSON on GET /api/status."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from iam_webserver.api.status import register

    status_path = tmp_path / "lidar-status.json"
    status_path.write_text(
        json.dumps(
            {
                "state": "streaming",
                "last_seq": 1,
                "last_seen_ts": time.time(),
                "has_baseline": True,
                "active_preset": "rig-a",
                "updated_at": time.time(),
            }
        )
    )

    app = web.Application()
    register(app, status_file=status_path, cache=_Cache(connected=True))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/status")
        assert response.status == 200
        data = await response.json()
        assert data["lidar"]["state"] == "streaming"
        assert data["lidar"]["active_preset"] == "rig-a"
        assert data["lidar"]["stream_connected"] is True
