"""Background client of lidar-service's frame socket.

The web-server connects to lidar-service as a second client of its Unix
domain socket (after touch-bridge) and caches the latest frame for use by
/api/status (freshness) and /api/calibration/capture (raw sensor-space
position of a touch). On any upstream loss the cache is cleared so callers
never receive stale data; the background task reconnects with exponential
backoff.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

_log = logging.getLogger(__name__)


class LidarFrameCache:
    """Holds the most recent frame received from lidar-service."""

    def __init__(
        self,
        *,
        socket_path: str,
        reconnect_initial_s: float,
        reconnect_max_s: float,
        reconnect_factor: float = 2.0,
    ) -> None:
        self._socket_path = socket_path
        self._initial_s = reconnect_initial_s
        self._max_s = reconnect_max_s
        self._factor = reconnect_factor
        self._latest: dict | None = None
        self._last_frame_ts: float | None = None
        self._connected = False
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def latest(self) -> dict | None:
        """The most recently received frame, or ``None`` if not connected."""
        return self._latest

    @property
    def last_frame_ts(self) -> float | None:
        """Wall-clock timestamp of the most recently received frame."""
        return self._last_frame_ts

    @property
    def connected(self) -> bool:
        """Whether a live connection to lidar-service is currently held."""
        return self._connected

    async def start(self) -> None:
        """Launch the background reader task."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="lidar-frame-cache")

    async def stop(self) -> None:
        """Stop the background task and tear the connection down."""
        self._stop.set()
        task = self._task
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
        self._task = None

    async def _run(self) -> None:
        backoff_s = self._initial_s
        while not self._stop.is_set():
            try:
                reader, writer = await asyncio.open_unix_connection(self._socket_path)
            except OSError as exc:
                _log.debug("lidar.sock connect failed (%s); backing off", exc)
                await self._sleep(backoff_s)
                backoff_s = min(backoff_s * self._factor, self._max_s)
                continue
            backoff_s = self._initial_s
            self._connected = True
            _log.info("lidar.sock connected (%s)", self._socket_path)
            try:
                await self._read_loop(reader)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
                self._connected = False
                self._latest = None
                self._last_frame_ts = None
                if not self._stop.is_set():
                    _log.warning("lidar.sock lost; will reconnect")

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while not self._stop.is_set():
            try:
                line = await reader.readline()
            except OSError:
                return
            if not line:  # EOF — upstream closed
                return
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                _log.warning("dropping malformed lidar frame")
                continue
            if isinstance(frame, dict):
                self._latest = frame
                self._last_frame_ts = time.time()

    async def _sleep(self, seconds: float) -> None:
        """Sleep that returns early when stop() is called."""
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
