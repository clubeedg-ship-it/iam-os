"""Core data types passed between lidar-service stages.

These are plain, immutable value objects. ``ScanSample`` is what a
``LidarDriver`` yields; ``Touch`` and ``TouchFrame`` are what the detection
pipeline produces.
"""

from __future__ import annotations

from dataclasses import dataclass

# A single LiDAR scan is a sequence of samples.
Scan = list["ScanSample"]


@dataclass(frozen=True, slots=True)
class ScanSample:
    """One LiDAR measurement, in polar coordinates relative to the sensor."""

    angle_deg: float
    """Bearing of the measurement, 0-360 degrees."""

    distance_mm: float
    """Range to the measured point, millimetres. Always > 0."""

    quality: int = 0
    """Driver-reported signal quality, 0 if the driver does not provide one."""


@dataclass(frozen=True, slots=True)
class TouchCandidate:
    """A detected touch before a stable id has been assigned.

    Produced by the detection pipeline and consumed by the tracker, which
    adds an id to turn it into a :class:`Touch`.
    """

    x: float
    y: float
    raw_x_mm: float
    raw_y_mm: float
    size: int


@dataclass(frozen=True, slots=True)
class Touch:
    """One detected touch.

    ``x`` / ``y`` are the calibrated, normalized position emitted downstream.
    ``raw_x_mm`` / ``raw_y_mm`` are the pre-calibration cartesian centroid,
    kept so the tracker can match touches between frames.
    """

    id: int
    x: float
    y: float
    raw_x_mm: float
    raw_y_mm: float
    size: int


@dataclass(frozen=True, slots=True)
class TouchFrame:
    """A complete frame of detected touches."""

    seq: int
    touches: tuple[Touch, ...] = ()

    @property
    def count(self) -> int:
        """Number of active touches; mirrors the touch-contract `count`."""
        return len(self.touches)
