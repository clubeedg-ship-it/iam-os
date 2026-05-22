"""Tests for the connection manager — backoff, watchdog, and scan delivery."""

import threading
import time

from iam_lidar.config import ConnectionConfig
from iam_lidar.connection import Backoff, ConnectionManager
from iam_lidar.drivers.base import DeviceInfo, LidarError
from iam_lidar.frames import ScanSample
from iam_lidar.health import HealthState


def _config(watchdog_timeout_s=1.0):
    return ConnectionConfig(
        backoff_initial_s=0.5,
        backoff_max_s=30.0,
        backoff_factor=2.0,
        watchdog_timeout_s=watchdog_timeout_s,
    )


# --- Backoff ---------------------------------------------------------------


def test_backoff_doubles_each_delay():
    backoff = Backoff(initial_s=0.5, maximum_s=30.0, factor=2.0)
    delays = [backoff.next_delay() for _ in range(7)]
    assert delays == [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0]


def test_backoff_caps_at_the_maximum():
    backoff = Backoff(initial_s=1.0, maximum_s=5.0, factor=2.0)
    for _ in range(10):
        backoff.next_delay()
    assert backoff.next_delay() == 5.0


def test_backoff_reset_returns_to_the_initial_delay():
    backoff = Backoff(initial_s=0.5, maximum_s=30.0, factor=2.0)
    backoff.next_delay()
    backoff.next_delay()
    backoff.reset()
    assert backoff.next_delay() == 0.5


# --- Reconnect with backoff (R3) -------------------------------------------


class _ConnectAlwaysFails:
    def __init__(self):
        self.connect_attempts = 0

    def connect(self):
        self.connect_attempts += 1
        raise LidarError("device not present")

    def read_scan(self):
        raise LidarError("not connected")

    def disconnect(self):
        pass


def test_connect_failure_retries_with_exponential_backoff():
    driver = _ConnectAlwaysFails()
    delays: list[float] = []
    manager: ConnectionManager

    def fake_sleep(seconds):
        delays.append(seconds)
        if len(delays) >= 4:
            manager.stop()

    manager = ConnectionManager(
        driver_factory=lambda: driver,
        on_scan=lambda scan: None,
        config=_config(),
        sleep=fake_sleep,
    )
    manager.run()

    assert delays == [0.5, 1.0, 2.0, 4.0]
    assert driver.connect_attempts == 4


# --- Scan delivery and health (R6) -----------------------------------------


class _Streams:
    def connect(self):
        return DeviceInfo(model="fake")

    def read_scan(self):
        return [ScanSample(angle_deg=0.0, distance_mm=1000.0)]

    def disconnect(self):
        pass


def test_scans_are_delivered_and_health_is_streaming():
    received: list = []
    manager: ConnectionManager

    def on_scan(scan):
        received.append(scan)
        if len(received) == 1:
            assert manager.health.state is HealthState.STREAMING
        if len(received) >= 3:
            manager.stop()

    manager = ConnectionManager(
        driver_factory=_Streams,
        on_scan=on_scan,
        config=_config(),
        sleep=lambda seconds: None,
    )
    manager.run()

    assert len(received) >= 3


# --- Watchdog (R4) ----------------------------------------------------------


class _Stalls:
    """Connects, but read_scan blocks far longer than the watchdog window."""

    def connect(self):
        return DeviceInfo(model="stalled")

    def read_scan(self):
        time.sleep(0.5)
        return [ScanSample(angle_deg=0.0, distance_mm=1000.0)]

    def disconnect(self):
        pass


def test_watchdog_detects_a_stalled_device_and_reconnects():
    created: list = []

    def factory():
        driver = _Stalls() if not created else _Streams()
        created.append(driver)
        return driver

    received: list = []
    manager: ConnectionManager

    def on_scan(scan):
        received.append(scan)
        manager.stop()

    manager = ConnectionManager(
        driver_factory=factory,
        on_scan=on_scan,
        config=_config(watchdog_timeout_s=0.1),
        sleep=lambda seconds: None,
    )
    manager.run()

    # The stalled driver tripped the watchdog; the manager built a fresh one.
    assert len(created) >= 2
    assert len(received) >= 1


def test_connection_lost_callback_fires_when_a_stream_drops():
    created: list = []

    def factory():
        driver = _Stalls() if not created else _Streams()
        created.append(driver)
        return driver

    losses: list = []
    manager: ConnectionManager

    def on_scan(scan):
        manager.stop()

    manager = ConnectionManager(
        driver_factory=factory,
        on_scan=on_scan,
        config=_config(watchdog_timeout_s=0.1),
        sleep=lambda seconds: None,
        on_connection_lost=lambda: losses.append(True),
    )
    manager.run()

    assert losses  # the dropped stall connection notified the consumer


# --- Reader-thread cleanup after a watchdog trip (C1) -----------------------


class _BlocksUntilDisconnected:
    """read_scan blocks on an Event; disconnect releases it — the contract.

    Models a hung device: read_scan never returns on its own. The
    ConnectionManager's only lever is disconnect(), which the LidarDriver
    contract requires to unblock a concurrent read_scan(). After a watchdog
    trip the manager must disconnect this driver *and join* its reader
    thread, so the thread is not leaked across the reconnect.

    Releasing the read does not let the reader exit immediately: it then
    spends a short, bounded time finishing (a real handle close is not
    instant). A manager that merely fires disconnect() and moves on leaves
    the thread alive; a manager that joins the reader waits it out.
    """

    def __init__(self):
        self._released = threading.Event()
        self.reader_thread: threading.Thread | None = None
        self.reading = threading.Event()

    def connect(self):
        return DeviceInfo(model="hung")

    def read_scan(self):
        # Record the thread the manager is reading us on, then block until
        # disconnect() releases us — exactly like a blocking serial read.
        self.reader_thread = threading.current_thread()
        self.reading.set()
        self._released.wait()
        # The handle does not tear down instantly once released.
        time.sleep(0.3)
        raise LidarError("device disconnected")

    def disconnect(self):
        self._released.set()


def test_watchdog_trip_joins_the_reader_thread_before_reconnecting():
    """After a watchdog trip the stalled reader must be gone before the
    next connection streams — the manager must join it, not leak it."""
    created: list = []

    def factory():
        driver = _BlocksUntilDisconnected() if not created else _Streams()
        created.append(driver)
        return driver

    manager: ConnectionManager
    hung_reader_alive_at_reconnect: list[bool] = []

    def on_scan(scan):
        # First scan from the fresh (_Streams) driver: by now the stalled
        # connection's reader thread must already have been joined.
        hung = created[0]
        if hung.reader_thread is not None:
            hung_reader_alive_at_reconnect.append(hung.reader_thread.is_alive())
        manager.stop()

    manager = ConnectionManager(
        driver_factory=factory,
        on_scan=on_scan,
        config=_config(watchdog_timeout_s=0.1),
        sleep=lambda seconds: None,
    )
    manager.run()

    assert len(created) >= 2  # watchdog tripped; manager built a fresh driver
    hung = created[0]
    assert isinstance(hung, _BlocksUntilDisconnected)
    assert hung.reading.is_set()  # the reader really entered the blocking read
    # The reader must not still be alive once the next connection streams...
    assert hung_reader_alive_at_reconnect == [False]
    # ...and must be fully terminated by the time run() returns.
    assert hung.reader_thread is not None
    assert not hung.reader_thread.is_alive()
