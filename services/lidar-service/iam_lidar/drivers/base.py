"""The LiDAR driver interface.

A driver hides the specifics of one sensor behind a uniform contract. All
reconnection, watchdog, and health logic lives *above* this interface, in the
ConnectionManager — so supporting a new sensor means writing one new driver
and nothing else (specs.md §6, R8).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from iam_lidar.frames import Scan


class LidarError(Exception):
    """A driver-level failure: the device could not be opened or read."""


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Identifies a connected device, for logging and health reporting."""

    model: str
    detail: str = ""


class LidarDriver(ABC):
    """Uniform interface to a LiDAR sensor."""

    @abstractmethod
    def connect(self) -> DeviceInfo:
        """Open the device.

        Returns information about the connected device, or raises
        :class:`LidarError` if it cannot be opened.
        """

    @abstractmethod
    def read_scan(self) -> Scan:
        """Return the next complete scan.

        Implementations must return within a bounded time — either a scan or
        a :class:`LidarError` if the device fails or stops responding. They
        must never block indefinitely; the ConnectionManager relies on this.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close the device. Safe to call even when not connected.

        MUST cause a :meth:`read_scan` running concurrently on another
        thread to return or raise :class:`LidarError` promptly: it is the
        only lever the ConnectionManager has to release a reader thread
        stuck in a blocking read on a hung device. ``disconnect()`` may be
        called from a thread other than the one inside ``read_scan``.
        """
