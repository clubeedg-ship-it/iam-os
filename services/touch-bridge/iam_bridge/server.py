"""The bridge WebSocket server.

Serves the touch-contract endpoint at ``ws://<host>:<port>`` and broadcasts
contract messages to every connected client — the launcher and the active
game. Clients only receive; they never send.
"""

from __future__ import annotations

import contextlib
import json
import logging

from websockets.asyncio.server import broadcast, serve

_log = logging.getLogger(__name__)


class BridgeServer:
    """Broadcasts touch-contract messages to all connected WebSocket clients."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._server: object | None = None
        self._stack = contextlib.AsyncExitStack()

    async def start(self) -> None:
        """Start listening for WebSocket clients."""
        self._server = await self._stack.enter_async_context(
            serve(self._handler, self._host, self._port)
        )
        _log.info("websocket server listening on ws://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        """Stop the server and close all client connections."""
        await self._stack.aclose()
        self._server = None

    def broadcast(self, message: dict) -> None:
        """Send a contract message to every connected client."""
        if self._server is not None:
            broadcast(self._server.connections, json.dumps(message))

    @property
    def client_count(self) -> int:
        """The number of currently connected clients."""
        return len(self._server.connections) if self._server is not None else 0

    async def _handler(self, websocket: object) -> None:
        """Hold a client connection open; the server tracks it for broadcasts."""
        await websocket.wait_closed()
