"""Baseline computation: the empty-surface reference for touch detection.

The baseline records the distance the LiDAR reads at each angle when nothing
is near the surface. During detection, a scan point markedly closer than the
baseline at the same angle indicates a touch.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from iam_lidar.frames import Scan


@dataclass(frozen=True, slots=True)
class Baseline:
    """An empty-surface reference: distance recorded per angle."""

    angles_deg: np.ndarray
    distances_mm: np.ndarray

    def distance_at(self, angle_deg: float) -> float:
        """Return the baseline distance at the recorded angle nearest ``angle_deg``."""
        index = int(np.argmin(np.abs(self.angles_deg - angle_deg)))
        return float(self.distances_mm[index])


def compute_baseline(
    scan: Scan,
    *,
    distance_min_mm: float,
    distance_max_mm: float,
    min_points: int,
) -> Baseline | None:
    """Build a :class:`Baseline` from a scan of the empty surface.

    Args:
        scan: a LiDAR scan of the surface with nothing near it.
        distance_min_mm: samples at or below this range are discarded.
        distance_max_mm: samples at or above this range are discarded.
        min_points: minimum in-range sample count for a usable baseline.

    Returns:
        A :class:`Baseline`, or ``None`` when fewer than ``min_points``
        samples fall within the valid range — too sparse to be reliable.
    """
    angles: list[float] = []
    distances: list[float] = []
    for sample in scan:
        if distance_min_mm < sample.distance_mm < distance_max_mm:
            angles.append(sample.angle_deg)
            distances.append(sample.distance_mm)

    if len(angles) < min_points:
        return None

    return Baseline(
        angles_deg=np.array(angles, dtype=float),
        distances_mm=np.array(distances, dtype=float),
    )
