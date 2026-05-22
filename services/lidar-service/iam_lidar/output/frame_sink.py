"""Publishes touch frames over a Unix domain socket.

lidar-service is the server; the touch-bridge (a separate service) connects
as a client and reads newline-delimited JSON frames. Frames are dropped when
no client is connected — the service never blocks on its output.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from pathlib import Path

from iam_lidar.frames import TouchFrame

_log = logging.getLogger(__name__)


def frame_to_dict(frame: TouchFrame) -> dict:
    """Convert a TouchFrame to the JSON-serializable shape sent downstream."""
    return {
        "seq": frame.seq,
        "count": frame.count,
        "touches": [
            {"id": touch.id, "x": touch.x, "y": touch.y} for touch in frame.touches
        ],
    }


class FrameSink:
    """A Unix-domain-socket server that broadcasts touch frames as JSON lines."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._server: socket.socket | None = None
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        """Bind the socket and begin accepting clients.

        Raises:
            OSError: if the socket cannot be created or bound.
        """
        path = Path(self._socket_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self._socket_path)
        server.listen(4)
        self._server = server
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        _log.info("frame sink listening on %s", self._socket_path)

    def publish(self, frame: TouchFrame) -> None:
        """Send a frame to every connected client; drop any that error."""
        line = (json.dumps(frame_to_dict(frame)) + "\n").encode()
        with self._lock:
            still_connected = []
            for client in self._clients:
                try:
                    client.sendall(line)
                    still_connected.append(client)
                except OSError:
                    self._close(client)
            self._clients = still_connected

    def close(self) -> None:
        """Stop accepting clients and close every socket."""
        self._running = False
        if self._server is not None:
            self._close(self._server)
            self._server = None
        with self._lock:
            for client in self._clients:
                self._close(client)
            self._clients = []
        Path(self._socket_path).unlink(missing_ok=True)

    def _accept_loop(self) -> None:
        """Accept incoming client connections until the sink is closed."""
        while self._running:
            # Capture the server reference once: a concurrent close() may set
            # self._server to None at any point, so re-reading it between the
            # None check and accept() would risk an AttributeError.
            server = self._server
            if server is None:
                return
            try:
                client, _ = server.accept()
            except OSError:
                return
            with self._lock:
                self._clients.append(client)
            _log.info("frame sink: client connected")

    @staticmethod
    def _close(sock: socket.socket) -> None:
        try:
            sock.close()
        except OSError:
            pass
