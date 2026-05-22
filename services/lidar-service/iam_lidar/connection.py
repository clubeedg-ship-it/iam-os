"""The connection manager — keeps the LiDAR connected and streaming.

This is where the reliability guarantee lives (specs.md §6). It owns the
driver lifecycle: connect with exponential backoff (R3), stream scans under a
watchdog that catches a stalled device (R4), and report health (R6). All of
it sits above the vendor-agnostic LidarDriver interface (R8), so it works
unchanged for any sensor.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

from iam_lidar.config import ConnectionConfig
from iam_lidar.drivers.base import LidarDriver, LidarError
from iam_lidar.frames import Scan
from iam_lidar.health import HealthReporter, HealthState

_log = logging.getLogger(__name__)

# Placed on the scan queue by the reader thread when the device fails.
_READER_FAILED = object()


class Backoff:
    """An exponential backoff delay sequence."""

    def __init__(self, *, initial_s: float, maximum_s: float, factor: float) -> None:
        self._initial_s = initial_s
        self._maximum_s = maximum_s
        self._factor = factor
        self._current_s = initial_s

    def next_delay(self) -> float:
        """Return the next delay, then advance the sequence (capped at maximum)."""
        delay = self._current_s
        self._current_s = min(self._current_s * self._factor, self._maximum_s)
        return delay

    def reset(self) -> None:
        """Return to the initial delay — call after a successful connection."""
        self._current_s = self._initial_s


class ConnectionManager:
    """Maintains a live LiDAR connection and delivers scans.

    :meth:`run` is a blocking loop, intended to run on its own thread: it
    connects, streams scans to ``on_scan``, and on any failure reconnects with
    exponential backoff. A watchdog detects a device that stops producing
    scans and forces a reconnect.
    """

    def __init__(
        self,
        *,
        driver_factory: Callable[[], LidarDriver],
        on_scan: Callable[[Scan], None],
        config: ConnectionConfig,
        health: HealthReporter | None = None,
        on_connection_lost: Callable[[], None] | None = None,
        sleep: Callable[[float], object] | None = None,
    ) -> None:
        self._driver_factory = driver_factory
        self._on_scan = on_scan
        self._config = config
        self._health = health or HealthReporter()
        self._on_connection_lost = on_connection_lost
        self._stop = threading.Event()
        # The default sleep is stop-aware: a pending shutdown ends a backoff
        # wait immediately instead of blocking for the full delay.
        self._sleep = sleep if sleep is not None else self._stop.wait
        self._backoff = Backoff(
            initial_s=config.backoff_initial_s,
            maximum_s=config.backoff_max_s,
            factor=config.backoff_factor,
        )

    @property
    def health(self) -> HealthReporter:
        """The health reporter, for the launcher to read."""
        return self._health

    def stop(self) -> None:
        """Ask the run loop to exit after the current iteration."""
        self._stop.set()

    def run(self) -> None:
        """Connect, stream, and reconnect until :meth:`stop` is called."""
        while not self._stop.is_set():
            driver = self._driver_factory()
            if self._connect(driver):
                self._backoff.reset()
                self._stream(driver)
                self._safe_disconnect(driver)
                if not self._stop.is_set() and self._on_connection_lost is not None:
                    self._on_connection_lost()
            else:
                self._safe_disconnect(driver)
            if not self._stop.is_set():
                self._sleep(self._backoff.next_delay())
        self._health.set(HealthState.DISCONNECTED)

    def _connect(self, driver: LidarDriver) -> bool:
        """Make one connection attempt; return True on success."""
        self._health.set(HealthState.CONNECTING)
        try:
            info = driver.connect()
        except LidarError as exc:
            _log.warning("connect failed: %s", exc)
            self._health.set(HealthState.FAILED)
            return False
        _log.info("connected: %s %s", info.model, info.detail)
        self._health.set(HealthState.STREAMING)
        return True

    def _stream(self, driver: LidarDriver) -> None:
        """Deliver scans until the device fails, stalls, or stop() is called."""
        scans: queue.Queue = queue.Queue(maxsize=2)
        reader_stop = threading.Event()
        reader = threading.Thread(
            target=self._read_loop,
            args=(driver, scans, reader_stop),
            daemon=True,
        )
        reader.start()
        try:
            while not self._stop.is_set():
                try:
                    item = scans.get(timeout=self._config.watchdog_timeout_s)
                except queue.Empty:
                    _log.warning(
                        "watchdog: no scan within %.1fs",
                        self._config.watchdog_timeout_s,
                    )
                    self._health.set(HealthState.STALE)
                    return
                if item is _READER_FAILED:
                    self._health.set(HealthState.FAILED)
                    return
                self._on_scan(item)
                self._health.set(HealthState.STREAMING)
        finally:
            reader_stop.set()

    def _read_loop(
        self,
        driver: LidarDriver,
        scans: queue.Queue,
        reader_stop: threading.Event,
    ) -> None:
        """Reader thread: pull scans from the driver onto the queue."""
        while not reader_stop.is_set() and not self._stop.is_set():
            try:
                scan = driver.read_scan()
            except LidarError as exc:
                _log.warning("scan read failed: %s", exc)
                self._offer(scans, _READER_FAILED)
                return
            self._offer(scans, scan)

    @staticmethod
    def _offer(scans: queue.Queue, item: object) -> None:
        """Put an item on the queue, dropping it if the consumer has stalled."""
        try:
            scans.put(item, timeout=1.0)
        except queue.Full:
            pass

    @staticmethod
    def _safe_disconnect(driver: LidarDriver) -> None:
        """Disconnect a driver; a failure during cleanup must not propagate."""
        try:
            driver.disconnect()
        except Exception as exc:
            _log.warning("disconnect failed: %s", exc)
