"""Tests for the lidar.sock client and latest-frame cache."""

import asyncio
import json
import socket
import tempfile
from pathlib import Path

import pytest

from iam_webserver.lidar_client import LidarFrameCache


class _MiniLidar:
    """Minimal Unix server that streams pre-baked lines to each client.

    Tracks live writers so a test can force a clean upstream disconnect —
    closing :class:`asyncio.start_unix_server` only closes the listener
    socket, not already-established connections, so a client blocked on
    ``readline`` would otherwise never observe the drop.
    """

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._writers: list[asyncio.StreamWriter] = []

    async def start(self, path: Path, lines: list[bytes]) -> None:
        async def handle(_reader, writer):
            self._writers.append(writer)
            for line in lines:
                writer.write(line)
                await writer.drain()
                await asyncio.sleep(0.005)
            # Hold the connection open until the test tears it down.
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass

        self._server = await asyncio.start_unix_server(handle, path=str(path))

    async def stop(self) -> None:
        for writer in list(self._writers):
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        self._writers.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


def _socket_path() -> Path:
    """A fresh, unused Unix-socket path."""
    return Path(tempfile.mkdtemp(prefix="iam-test-")) / "lidar.sock"


def _check_unix_sockets() -> None:
    if not hasattr(socket, "AF_UNIX"):  # pragma: no cover - platform guard
        pytest.skip("AF_UNIX unavailable on this platform")


async def test_starts_with_no_frame_and_disconnected() -> None:
    _check_unix_sockets()
    path = _socket_path()
    cache = LidarFrameCache(
        socket_path=str(path),
        reconnect_initial_s=0.05,
        reconnect_max_s=0.2,
    )
    assert cache.latest is None
    assert cache.connected is False


async def test_cache_picks_up_a_frame_from_the_socket() -> None:
    _check_unix_sockets()
    path = _socket_path()
    frame = {
        "seq": 1,
        "count": 1,
        "touches": [
            {"id": 4, "x": 0.5, "y": 0.5, "raw_x_mm": 200.0, "raw_y_mm": 300.0}
        ],
    }
    server = _MiniLidar()
    await server.start(path, [json.dumps(frame).encode() + b"\n"])
    cache = LidarFrameCache(
        socket_path=str(path), reconnect_initial_s=0.05, reconnect_max_s=0.2
    )
    await cache.start()
    try:
        deadline = asyncio.get_event_loop().time() + 2.0
        while cache.latest is None and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert cache.latest == frame
        assert cache.connected is True
        assert cache.last_frame_ts is not None
    finally:
        await cache.stop()
        await server.stop()


async def test_cache_updates_on_every_new_frame() -> None:
    _check_unix_sockets()
    path = _socket_path()
    frames = [
        {"seq": i, "count": 0, "touches": []} for i in range(1, 4)
    ]
    server = _MiniLidar()
    await server.start(path, [json.dumps(f).encode() + b"\n" for f in frames])
    cache = LidarFrameCache(
        socket_path=str(path), reconnect_initial_s=0.05, reconnect_max_s=0.2
    )
    await cache.start()
    try:
        deadline = asyncio.get_event_loop().time() + 2.0
        while (
            (cache.latest or {}).get("seq") != 3
            and asyncio.get_event_loop().time() < deadline
        ):
            await asyncio.sleep(0.01)
        assert cache.latest is not None
        assert cache.latest["seq"] == 3
    finally:
        await cache.stop()
        await server.stop()


async def test_malformed_line_does_not_kill_the_task() -> None:
    _check_unix_sockets()
    path = _socket_path()
    good = {"seq": 9, "count": 0, "touches": []}
    server = _MiniLidar()
    await server.start(
        path, [b"this is not json\n", json.dumps(good).encode() + b"\n"]
    )
    cache = LidarFrameCache(
        socket_path=str(path), reconnect_initial_s=0.05, reconnect_max_s=0.2
    )
    await cache.start()
    try:
        deadline = asyncio.get_event_loop().time() + 2.0
        while cache.latest is None and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert cache.latest == good
    finally:
        await cache.stop()
        await server.stop()


async def test_cache_clears_on_upstream_drop_and_reconnects() -> None:
    _check_unix_sockets()
    path = _socket_path()
    frame = {"seq": 7, "count": 0, "touches": []}
    server = _MiniLidar()
    await server.start(path, [json.dumps(frame).encode() + b"\n"])
    cache = LidarFrameCache(
        socket_path=str(path), reconnect_initial_s=0.05, reconnect_max_s=0.1
    )
    await cache.start()
    try:
        # First connection: frame arrives.
        deadline = asyncio.get_event_loop().time() + 2.0
        while cache.latest is None and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert cache.latest == frame
        assert cache.connected is True

        # Tear down upstream: the cache must observe the disconnect and stop
        # reporting "connected" while it backs off.
        await server.stop()
        deadline = asyncio.get_event_loop().time() + 2.0
        while cache.connected and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert cache.connected is False
        assert cache.latest is None  # stale data is never surfaced

        # Bring upstream back up: the cache reconnects on its own.
        new_frame = {"seq": 99, "count": 0, "touches": []}
        server = _MiniLidar()
        await server.start(path, [json.dumps(new_frame).encode() + b"\n"])
        deadline = asyncio.get_event_loop().time() + 3.0
        while (
            (cache.latest or {}).get("seq") != 99
            and asyncio.get_event_loop().time() < deadline
        ):
            await asyncio.sleep(0.02)
        assert cache.latest == new_frame
        assert cache.connected is True
    finally:
        await cache.stop()
        await server.stop()


async def test_stop_terminates_the_background_task() -> None:
    _check_unix_sockets()
    path = _socket_path()
    cache = LidarFrameCache(
        socket_path=str(path), reconnect_initial_s=0.05, reconnect_max_s=0.1
    )
    await cache.start()
    await cache.stop()
    # A second stop is a no-op.
    await cache.stop()
