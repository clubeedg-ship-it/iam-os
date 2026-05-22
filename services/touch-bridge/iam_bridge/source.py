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
import time
from collections.abc import Callable

_log = logging.getLogger(__name__)

# Reconnect backoff bounds. lidar-service is the socket server; when it is
# down a connect attempt fails fast, and the bridge's main loop calls
# next_frame() every heartbeat (~1s). Without backoff that is a tight
# reconnect loop against a dead upstream, so failed attempts are spaced by a
# delay that doubles from the initial value up to the maximum. A successful
# connection resets it (mirrors lidar-service's connection.Backoff).
_BACKOFF_INITIAL_S = 0.5
_BACKOFF_MAX_S = 10.0
# Multiplier applied after each failed attempt.
_BACKOFF_FACTOR = 2.0


class FrameSource:
    """An async client for the lidar-service touch-frame socket."""

    def __init__(
        self,
        socket_path: str,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._socket_path = socket_path
        # Injectable clock so the reconnect backoff can be tested without
        # real waiting; defaults to the wall-clock monotonic timer.
        self._monotonic = monotonic
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        # Reconnect backoff state. ``_next_attempt_at`` is the monotonic time
        # before which no connect attempt is made; ``_backoff_s`` is the delay
        # applied after the next failure. Both reset on a successful connect.
        self._next_attempt_at = 0.0
        self._backoff_s = _BACKOFF_INITIAL_S

    async def next_frame(self, timeout: float) -> dict | None:
        """Return the next upstream frame, or None.

        None is returned when no frame arrives within ``timeout``, when
        upstream is unavailable, or when a malformed line is received.

        While disconnected, connect attempts are rate-limited by an
        exponential backoff: if called before the backoff has elapsed, this
        returns None immediately without attempting to connect.
        """
        if self._reader is None:
            if self._monotonic() < self._next_attempt_at:
                return None
            if not await self._connect():
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
            # Schedule the next attempt and grow the backoff (capped).
            self._next_attempt_at = self._monotonic() + self._backoff_s
            self._backoff_s = min(self._backoff_s * _BACKOFF_FACTOR, _BACKOFF_MAX_S)
            return False
        _log.info("upstream connected: %s", self._socket_path)
        self._connected = True
        # Connection restored: clear the backoff so a future drop starts fresh.
        self._next_attempt_at = 0.0
        self._backoff_s = _BACKOFF_INITIAL_S
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
