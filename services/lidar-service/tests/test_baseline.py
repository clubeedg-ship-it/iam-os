"""Tests for baseline computation — the empty-surface reference scan."""

from iam_lidar.detection.baseline import compute_baseline
from iam_lidar.frames import ScanSample


def _scan(samples):
    """Build a scan from (angle_deg, distance_mm) pairs."""
    return [ScanSample(angle_deg=a, distance_mm=d) for a, d in samples]


def test_too_few_points_returns_none():
    scan = _scan([(float(i), 2000.0) for i in range(5)])
    baseline = compute_baseline(
        scan, distance_min_mm=200, distance_max_mm=6000, min_points=10
    )
    assert baseline is None


def test_enough_points_returns_a_baseline():
    scan = _scan([(float(i), 2000.0) for i in range(20)])
    baseline = compute_baseline(
        scan, distance_min_mm=200, distance_max_mm=6000, min_points=10
    )
    assert baseline is not None


def test_out_of_range_distances_are_excluded():
    in_range = [(float(i), 2000.0) for i in range(12)]
    too_close = [(float(i + 100), 50.0) for i in range(12)]  # below distance_min
    baseline = compute_baseline(
        _scan(in_range + too_close),
        distance_min_mm=200,
        distance_max_mm=6000,
        min_points=10,
    )
    # Only the 12 in-range samples (angles 0-11) count toward min_points.
    assert baseline is not None
    assert baseline.distance_at(5.0) == 2000.0


def test_distance_at_exact_angle():
    scan = _scan([(float(i), 1000.0 + i) for i in range(20)])
    baseline = compute_baseline(
        scan, distance_min_mm=200, distance_max_mm=6000, min_points=10
    )
    assert baseline.distance_at(7.0) == 1007.0


def test_distance_at_uses_the_nearest_recorded_angle():
    # Angles 0, 10, 20, ... ; querying 23 should resolve to angle 20.
    scan = _scan([(float(i * 10), 1000.0 + i) for i in range(20)])
    baseline = compute_baseline(
        scan, distance_min_mm=200, distance_max_mm=6000, min_points=10
    )
    assert baseline.distance_at(23.0) == 1002.0
