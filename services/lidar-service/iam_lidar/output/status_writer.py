"""Publishes lidar-service health and tracking state to a JSON file.

The launcher's web-server reads this file to power its status view and the
calibrate view's freshness indicator. The file is written atomically
(write-and-rename) so a reader never sees a half-written document; it is
refreshed on every health transition and at a configurable heartbeat so a
stuck service is visible as a stale ``updated_at`` timestamp.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from iam_lidar.health import HealthReporter, HealthState

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    """Volatile fields the status writer samples at each write."""

    last_seq: int
    last_seen_ts: float
    has_baseline: bool
    active_preset: str


class StatusWriter:
    """Writes lidar-service status to a JSON file.

    Combines a steady ``HealthReporter`` state with a sampled snapshot
    of tracking fields. Writes happen on three triggers:

    * a manual :meth:`write_now` from the entry point,
    * every health transition (via a listener on the reporter),
    * a fixed heartbeat thread, started with :meth:`start_heartbeat`.

    Passing ``path=None`` disables the writer entirely so configuration can
    turn status reporting off without forking the call sites.
    """

    def __init__(
        self,
        *,
        path: Path | str | None,
        health: HealthReporter,
        snapshot: Callable[[], StatusSnapshot],
        heartbeat_interval_s: float = 1.0,
    ) -> None:
        self._path = Path(path) if path else None
        self._health = health
        self._snapshot = snapshot
        self._heartbeat_interval_s = heartbeat_interval_s
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._attached = False

    def attach(self) -> None:
        """Listen to health transitions so each one triggers a fresh write."""
        if self._attached:
            return
        self._health.add_listener(self._on_health_change)
        self._attached = True

    def detach(self) -> None:
        """Stop listening to health transitions."""
        if not self._attached:
            return
        self._health.remove_listener(self._on_health_change)
        self._attached = False

    def start_heartbeat(self) -> None:
        """Begin periodic writes on a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._heartbeat_loop, name="status-heartbeat", daemon=True
        )
        self._thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the heartbeat thread; safe to call repeatedly."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def write_now(self) -> None:
        """Sample the snapshot + health state and write the status file."""
        if self._path is None:
            return
        payload = {
            "state": self._health.state.value,
            **asdict(self._snapshot()),
            "updated_at": time.time(),
        }
        try:
            self._write_atomically(payload)
        except OSError as exc:
            _log.warning("status file write failed (%s): %s", self._path, exc)

    def _on_health_change(self, _state: HealthState) -> None:
        self.write_now()

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            self.write_now()
            self._stop.wait(self._heartbeat_interval_s)

    def _write_atomically(self, payload: dict) -> None:
        assert self._path is not None
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, self._path)
