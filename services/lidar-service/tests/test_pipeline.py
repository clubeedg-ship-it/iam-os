"""Tests for the touch-detection pipeline.

Exercises the full chain — scan -> baseline -> touch points -> cluster ->
calibrate -> track — with hand-built scans (no hardware, no driver).
"""

from iam_lidar.config import DetectionConfig
from iam_lidar.detection.calibration import Calibration
from iam_lidar.frames import ScanSample
from iam_lidar.pipeline import Pipeline

DETECTION = DetectionConfig(
    distance_min_mm=200,
    distance_max_mm=6000,
    baseline_threshold_mm=150,
    baseline_min_points=10,
    cluster_tolerance_mm=100,
    cluster_min_points=8,
    cluster_max_points=300,
    track_tolerance_mm=150,
)


def _flat_scan(distance_mm=2000.0):
    """A full 360-degree scan of an empty surface at a uniform distance."""
    return [ScanSample(angle_deg=float(a), distance_mm=distance_mm) for a in range(360)]


def _scan_with_object(center_deg, distance_mm=1000.0, width=12):
    """An empty-surface scan with a closer object spanning a few degrees."""
    scan = _flat_scan()
    for i in range(width):
        angle = (center_deg - width // 2 + i) % 360
        scan[angle] = ScanSample(angle_deg=float(angle), distance_mm=distance_mm)
    return scan


def test_no_baseline_yields_an_empty_frame():
    pipeline = Pipeline(DETECTION)
    assert pipeline.process(_flat_scan()).count == 0


def test_set_baseline_rejects_a_too_sparse_scan():
    pipeline = Pipeline(DETECTION)
    sparse = [ScanSample(angle_deg=float(a), distance_mm=2000.0) for a in range(5)]
    assert pipeline.set_baseline(sparse) is False
    assert pipeline.has_baseline is False


def test_set_baseline_accepts_a_full_scan():
    pipeline = Pipeline(DETECTION)
    assert pipeline.set_baseline(_flat_scan()) is True
    assert pipeline.has_baseline is True


def test_empty_surface_produces_no_touches():
    pipeline = Pipeline(DETECTION)
    pipeline.set_baseline(_flat_scan())
    assert pipeline.process(_flat_scan()).count == 0


def test_a_closer_object_is_detected_as_a_touch():
    pipeline = Pipeline(DETECTION)
    pipeline.set_baseline(_flat_scan())
    assert pipeline.process(_scan_with_object(center_deg=90)).count == 1


def test_sequence_number_increments_each_frame():
    pipeline = Pipeline(DETECTION)
    pipeline.set_baseline(_flat_scan())
    first = pipeline.process(_flat_scan())
    second = pipeline.process(_flat_scan())
    assert second.seq == first.seq + 1


def test_a_touch_keeps_its_id_across_frames():
    pipeline = Pipeline(DETECTION)
    pipeline.set_baseline(_flat_scan())
    first = pipeline.process(_scan_with_object(center_deg=90))
    second = pipeline.process(_scan_with_object(center_deg=91))
    assert first.touches[0].id == second.touches[0].id


def test_without_calibration_a_touch_maps_to_the_centre():
    pipeline = Pipeline(DETECTION)
    pipeline.set_baseline(_flat_scan())
    touch = pipeline.process(_scan_with_object(center_deg=90)).touches[0]
    assert (touch.x, touch.y) == (0.5, 0.5)


def test_calibration_is_applied_to_touch_coordinates():
    pipeline = Pipeline(DETECTION)
    pipeline.set_baseline(_flat_scan())
    corners = [
        (-2000.0, -2000.0),
        (2000.0, -2000.0),
        (2000.0, 2000.0),
        (-2000.0, 2000.0),
    ]
    pipeline.set_calibration(Calibration.from_corners(corners))
    touch = pipeline.process(_scan_with_object(center_deg=90)).touches[0]
    assert 0.0 <= touch.x <= 1.0
    assert 0.0 <= touch.y <= 1.0
    assert (touch.x, touch.y) != (0.5, 0.5)
