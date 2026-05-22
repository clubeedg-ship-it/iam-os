"""Tests for calibration — the perspective transform from sensor space to
normalized surface coordinates."""

import pytest

from iam_lidar.detection.calibration import Calibration

# Corners in top-left, top-right, bottom-right, bottom-left order.
UNIT_SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def test_from_corners_rejects_wrong_corner_count():
    with pytest.raises(ValueError):
        Calibration.from_corners([(0.0, 0.0), (1.0, 0.0)])


def test_identity_when_source_equals_unit_square():
    cal = Calibration.from_corners(UNIT_SQUARE)
    assert cal.map_point(0.5, 0.5) == pytest.approx((0.5, 0.5))


def test_source_corners_map_to_destination_corners():
    source = [(100.0, 200.0), (1100.0, 150.0), (1200.0, 1300.0), (50.0, 1250.0)]
    cal = Calibration.from_corners(source)
    for (sx, sy), expected in zip(source, UNIT_SQUARE):
        assert cal.map_point(sx, sy) == pytest.approx(expected, abs=1e-9)


def test_scaled_square_maps_proportionally():
    source = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
    cal = Calibration.from_corners(source)
    assert cal.map_point(500.0, 500.0) == pytest.approx((0.5, 0.5))
    assert cal.map_point(250.0, 750.0) == pytest.approx((0.25, 0.75))


def test_points_outside_the_quad_are_clamped_to_unit_range():
    source = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
    cal = Calibration.from_corners(source)
    assert cal.map_point(-500.0, 2000.0) == (0.0, 1.0)


def test_custom_destination_corners_change_orientation():
    source = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
    # Destination corners rotated 180 degrees -> a full flip.
    flipped = [(1.0, 1.0), (0.0, 1.0), (0.0, 0.0), (1.0, 0.0)]
    cal = Calibration.from_corners(source, dest_corners=flipped)
    assert cal.map_point(0.0, 0.0) == pytest.approx((1.0, 1.0))
    assert cal.map_point(250.0, 250.0) == pytest.approx((0.75, 0.75))
