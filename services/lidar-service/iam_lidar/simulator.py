"""A LiDAR driver that produces synthetic scans — no hardware required.

The simulator emits a full 360-degree background ring with one slowly
orbiting object, so the detection pipeline and the whole service can be
exercised end to end without a sensor (specs.md §9). It implements the same
:class:`~iam_lidar.drivers.base.LidarDriver` interface as the real sensor.
"""

from __future__ import annotations

import math

from iam_lidar.drivers.base import DeviceInfo, LidarDriver, LidarError
from iam_lidar.frames import Scan, ScanSample

_BACKGROUND_DISTANCE_MM = 2000.0
_OBJECT_DISTANCE_MM = 1000.0
_OBJECT_HALF_WIDTH_DEG = 6
_TICK_SECONDS = 0.033


class SimDriver(LidarDriver):
    """Generates synthetic scans for hardware-free development and testing."""

    def __init__(self) -> None:
        self._connected = False
        self._elapsed_s = 0.0

    def connect(self) -> DeviceInfo:
        self._connected = True
        return DeviceInfo(model="simulator", detail="synthetic LiDAR")

    def read_scan(self) -> Scan:
        if not self._connected:
            raise LidarError("simulator is not connected")
        self._elapsed_s += _TICK_SECONDS
        return self._synthetic_scan()

    def disconnect(self) -> None:
        self._connected = False

    def _synthetic_scan(self) -> Scan:
        """A 360-degree background ring with one slowly orbiting object."""
        scan = [
            ScanSample(angle_deg=float(angle), distance_mm=_BACKGROUND_DISTANCE_MM)
            for angle in range(360)
        ]
        center = 180.0 + 80.0 * math.sin(self._elapsed_s * 0.8)
        for offset in range(-_OBJECT_HALF_WIDTH_DEG, _OBJECT_HALF_WIDTH_DEG + 1):
            angle = int(center + offset) % 360
            scan[angle] = ScanSample(
                angle_deg=float(angle), distance_mm=_OBJECT_DISTANCE_MM
            )
        return scan
