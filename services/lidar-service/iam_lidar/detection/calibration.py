"""Calibration: the perspective transform from sensor space to the
normalized projection surface.

A four-corner homography maps LiDAR-space millimetres to surface coordinates
in the unit square. Orientation — any flip or rotation — is expressed by the
choice of destination corners; nothing is hardcoded (specs.md §7). The
homography is solved with NumPy, so the service does not depend on OpenCV.
"""

from __future__ import annotations

import numpy as np

Point = tuple[float, float]

# Surface corners in top-left, top-right, bottom-right, bottom-left order.
UNIT_SQUARE: list[Point] = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def _homography(source: list[Point], dest: list[Point]) -> np.ndarray:
    """Solve the 3x3 homography mapping four source corners to four dest corners."""
    a = np.zeros((8, 8), dtype=float)
    b = np.zeros(8, dtype=float)
    for i, ((x, y), (u, v)) in enumerate(zip(source, dest)):
        a[2 * i] = [x, y, 1.0, 0.0, 0.0, 0.0, -x * u, -y * u]
        a[2 * i + 1] = [0.0, 0.0, 0.0, x, y, 1.0, -x * v, -y * v]
        b[2 * i] = u
        b[2 * i + 1] = v
    h = np.linalg.solve(a, b)
    return np.array(
        [
            [h[0], h[1], h[2]],
            [h[3], h[4], h[5]],
            [h[6], h[7], 1.0],
        ]
    )


class Calibration:
    """Maps sensor-space points to normalized surface coordinates."""

    def __init__(self, matrix: np.ndarray) -> None:
        self._matrix = matrix

    @classmethod
    def from_corners(
        cls,
        source_corners: list[Point],
        dest_corners: list[Point] | None = None,
    ) -> "Calibration":
        """Build a calibration from four surface corners.

        Args:
            source_corners: the four surface corners in sensor space (mm), in
                top-left, top-right, bottom-right, bottom-left order.
            dest_corners: where those corners land in normalized space;
                defaults to the unit square. Supply rotated or flipped
                corners to set the projection's orientation.

        Raises:
            ValueError: if either corner list does not contain exactly four
                points.
        """
        if len(source_corners) != 4:
            raise ValueError(f"expected 4 source corners, got {len(source_corners)}")
        dest = dest_corners if dest_corners is not None else UNIT_SQUARE
        if len(dest) != 4:
            raise ValueError(f"expected 4 destination corners, got {len(dest)}")
        return cls(_homography(source_corners, dest))

    def map_point(self, x_mm: float, y_mm: float) -> Point:
        """Map a sensor-space point to normalized surface coordinates.

        The result is clamped to ``[0, 1]`` on both axes so downstream
        consumers always receive in-bounds coordinates, as the touch contract
        requires.
        """
        u, v, w = self._matrix @ np.array([x_mm, y_mm, 1.0])
        return (
            min(1.0, max(0.0, float(u / w))),
            min(1.0, max(0.0, float(v / w))),
        )
