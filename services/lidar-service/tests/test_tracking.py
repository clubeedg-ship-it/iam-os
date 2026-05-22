"""Tests for the touch tracker — stable id assignment across frames."""

from iam_lidar.detection.tracking import Tracker
from iam_lidar.frames import TouchCandidate


def _candidate(raw_x, raw_y):
    """A candidate at a raw sensor position; normalized coords unused here."""
    return TouchCandidate(x=0.5, y=0.5, raw_x_mm=raw_x, raw_y_mm=raw_y, size=10)


def test_first_frame_assigns_fresh_unique_ids():
    tracker = Tracker(tolerance_mm=150.0)
    touches = tracker.assign_ids(
        [_candidate(0, 0), _candidate(500, 0), _candidate(1000, 0)]
    )
    assert [t.id for t in touches] == [1, 2, 3]


def test_touch_near_its_previous_position_keeps_its_id():
    tracker = Tracker(tolerance_mm=150.0)
    tracker.assign_ids([_candidate(0, 0)])  # frame 1 -> id 1
    touches = tracker.assign_ids([_candidate(30, 0)])  # moved 30 mm
    assert [t.id for t in touches] == [1]


def test_touch_far_from_all_previous_gets_a_new_id():
    tracker = Tracker(tolerance_mm=150.0)
    tracker.assign_ids([_candidate(0, 0)])  # id 1
    touches = tracker.assign_ids([_candidate(5000, 5000)])
    assert touches[0].id == 2


def test_each_previous_id_is_reused_at_most_once():
    tracker = Tracker(tolerance_mm=150.0)
    tracker.assign_ids([_candidate(0, 0)])  # one previous touch, id 1
    # Two candidates both near the previous touch; only the first claims id 1.
    touches = tracker.assign_ids([_candidate(10, 0), _candidate(20, 0)])
    assert touches[0].id == 1
    assert touches[1].id == 2


def test_new_ids_keep_incrementing_and_are_not_recycled():
    tracker = Tracker(tolerance_mm=150.0)
    tracker.assign_ids([_candidate(0, 0)])  # id 1
    tracker.assign_ids([_candidate(9000, 0)])  # id 2, id 1 retired
    touches = tracker.assign_ids([_candidate(0, 9000)])  # id 3, never recycles 1
    assert touches[0].id == 3


def test_reset_clears_previous_frame_state():
    tracker = Tracker(tolerance_mm=150.0)
    tracker.assign_ids([_candidate(0, 0)])  # id 1
    tracker.reset()
    # After reset there is no previous frame to match against.
    touches = tracker.assign_ids([_candidate(0, 0)])
    assert touches[0].id == 2


def test_assigned_touch_carries_candidate_fields():
    tracker = Tracker(tolerance_mm=150.0)
    [touch] = tracker.assign_ids(
        [TouchCandidate(x=0.25, y=0.75, raw_x_mm=120.0, raw_y_mm=340.0, size=17)]
    )
    assert (touch.x, touch.y, touch.raw_x_mm, touch.raw_y_mm, touch.size) == (
        0.25,
        0.75,
        120.0,
        340.0,
        17,
    )
