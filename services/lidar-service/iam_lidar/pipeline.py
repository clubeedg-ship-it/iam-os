"""The touch-detection pipeline.

Turns a raw LiDAR scan into a frame of identified touches:

    scan -> touch points (baseline difference) -> clusters -> centroids
         -> calibrated coordinates -> stable ids

The pipeline is stateful: it holds the captured baseline, the active
calibration, the tracker, and a frame counter.
"""

from __future__ import annotations

import math

from iam_lidar.config import DetectionConfig
from iam_lidar.detection.baseline import Baseline, compute_baseline
from iam_lidar.detection.calibration import Calibration
from iam_lidar.detection.clustering import Point, cluster_points
from iam_lidar.detection.tracking import Tracker
from iam_lidar.frames import Scan, TouchCandidate, TouchFrame

_UNCALIBRATED_POSITION = (0.5, 0.5)


class Pipeline:
    """Detects and tracks touches across successive LiDAR scans."""

    def __init__(
        self,
        detection: DetectionConfig,
        *,
        calibration: Calibration | None = None,
    ) -> None:
        self._detection = detection
        self._calibration = calibration
        self._baseline: Baseline | None = None
        self._tracker = Tracker(tolerance_mm=detection.track_tolerance_mm)
        self._seq = 0

    @property
    def has_baseline(self) -> bool:
        """Whether a usable empty-surface baseline has been captured."""
        return self._baseline is not None

    def set_baseline(self, scan: Scan) -> bool:
        """Capture the empty-surface baseline from a scan.

        Returns ``False`` (and leaves any existing baseline unchanged) when
        the scan is too sparse to be a reliable reference.
        """
        baseline = compute_baseline(
            scan,
            distance_min_mm=self._detection.distance_min_mm,
            distance_max_mm=self._detection.distance_max_mm,
            min_points=self._detection.baseline_min_points,
        )
        if baseline is None:
            return False
        self._baseline = baseline
        return True

    def set_calibration(self, calibration: Calibration) -> None:
        """Install the calibration used to map touches to surface coordinates."""
        self._calibration = calibration

    def reset_tracking(self) -> None:
        """Drop cross-frame tracking state after a gap in scan data."""
        self._tracker.reset()

    def process(self, scan: Scan) -> TouchFrame:
        """Run one scan through the pipeline and return a frame of touches.

        With no baseline captured, or an empty scan, an empty frame is
        returned and tracking state is left untouched.
        """
        self._seq += 1
        if self._baseline is None or not scan:
            return TouchFrame(seq=self._seq)

        candidates: list[TouchCandidate] = []
        for cluster in cluster_points(
            self._touch_points(scan),
            tolerance_mm=self._detection.cluster_tolerance_mm,
        ):
            candidate = self._candidate(cluster)
            if candidate is not None:
                candidates.append(candidate)

        touches = self._tracker.assign_ids(candidates)
        return TouchFrame(seq=self._seq, touches=tuple(touches))

    def _touch_points(self, scan: Scan) -> list[Point]:
        """Cartesian points where the scan reads closer than the baseline."""
        assert self._baseline is not None  # guarded by process()
        points: list[Point] = []
        for sample in scan:
            distance = sample.distance_mm
            if not (
                self._detection.distance_min_mm
                < distance
                < self._detection.distance_max_mm
            ):
                continue
            baseline_distance = self._baseline.distance_at(sample.angle_deg)
            if baseline_distance - distance > self._detection.baseline_threshold_mm:
                radians = math.radians(sample.angle_deg)
                points.append(
                    (distance * math.cos(radians), distance * math.sin(radians))
                )
        return points

    def _candidate(self, cluster: list[Point]) -> TouchCandidate | None:
        """Reduce one cluster to a touch candidate, or None if out of size bounds."""
        size = len(cluster)
        if not (
            self._detection.cluster_min_points
            <= size
            <= self._detection.cluster_max_points
        ):
            return None
        raw_x = sum(point[0] for point in cluster) / size
        raw_y = sum(point[1] for point in cluster) / size
        if self._calibration is not None:
            x, y = self._calibration.map_point(raw_x, raw_y)
        else:
            x, y = _UNCALIBRATED_POSITION
        return TouchCandidate(x=x, y=y, raw_x_mm=raw_x, raw_y_mm=raw_y, size=size)
