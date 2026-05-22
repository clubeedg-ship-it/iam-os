"""Reads touch frames from lidar-service over a Unix domain socket.

lidar-service is the socket server; the bridge is the client. The source
reconnects automatically when lidar-service is unavailable or restarts, and
reports an empty result rather than blocking — so the bridge can fall back to
heartbeat frames and consumers never see stale data.
"""

from __future__ import annotations

import asyncio
import json
import logging

_log = logging.getLogger(__name__)


class FrameSource:
    """An async client for the lidar-service touch-frame socket."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False

    async def next_frame(self, timeout: float) -> dict | None:
        """Return the next upstream frame, or None.

        None is returned when no frame arrives within ``timeout``, when
        upstream is unavailable, or when a malformed line is received.
        """
        if self._reader is None and not await self._connect():
            return None
        assert self._reader is not None
        try:
            line = await asyncio.wait_for(self._reader.readline(), timeout)
        except TimeoutError:
            return None
        except OSError:
            await self._disconnect()
            return None
        if not line:  # EOF: upstream closed the connection
            await self._disconnect()
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            _log.warning("discarding malformed upstream frame")
            return None

    async def close(self) -> None:
        """Close the upstream connection."""
        await self._disconnect()

    async def _connect(self) -> bool:
        try:
            self._reader, self._writer = await asyncio.open_unix_connection(
                self._socket_path
            )
        except OSError:
            return False
        _log.info("upstream connected: %s", self._socket_path)
        self._connected = True
        return True

    async def _disconnect(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        self._reader = None
        self._writer = None
        if self._connected:
            _log.warning("upstream lost: %s", self._socket_path)
            self._connected = False
