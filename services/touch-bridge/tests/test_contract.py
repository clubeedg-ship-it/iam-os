"""Tests for the touch-contract message builder.

Every message the bridge emits must conform to docs/touch-contract.schema.json.
"""

import json
from pathlib import Path

import jsonschema

from iam_bridge.contract import empty_message, to_contract_message

_SCHEMA = json.loads(
    (Path(__file__).parents[3] / "docs" / "touch-contract.schema.json").read_text()
)


def _assert_valid(message):
    jsonschema.validate(message, _SCHEMA)


def test_empty_message_is_schema_valid():
    message = empty_message(seq=1)
    _assert_valid(message)
    assert message == {"seq": 1, "count": 0, "touches": []}


def test_contract_message_from_an_upstream_frame_is_schema_valid():
    upstream = {"seq": 99, "count": 1, "touches": [{"id": 4, "x": 0.3, "y": 0.6}]}
    _assert_valid(to_contract_message(upstream, seq=7))


def test_message_uses_the_supplied_sequence_number():
    upstream = {"seq": 99, "count": 0, "touches": []}
    assert to_contract_message(upstream, seq=42)["seq"] == 42


def test_count_matches_the_number_of_touches():
    upstream = {
        "count": 0,  # deliberately wrong; the bridge recomputes it
        "touches": [
            {"id": 1, "x": 0.1, "y": 0.2},
            {"id": 2, "x": 0.3, "y": 0.4},
        ],
    }
    assert to_contract_message(upstream, seq=1)["count"] == 2


def test_coordinates_are_clamped_to_the_unit_range():
    upstream = {"touches": [{"id": 1, "x": 1.5, "y": -0.2}]}
    touch = to_contract_message(upstream, seq=1)["touches"][0]
    assert touch["x"] == 1.0
    assert touch["y"] == 0.0


def test_only_contract_fields_are_kept():
    """The bridge strips every field except id/x/y, so the frozen public
    contract is unchanged even though lidar-service now sends raw_x_mm /
    raw_y_mm on its private wire for the launcher's calibration flow.
    """
    upstream = {
        "touches": [
            {
                "id": 1,
                "x": 0.5,
                "y": 0.5,
                "raw_x_mm": 100.0,
                "raw_y_mm": 200.0,
                "size": 12,
            }
        ]
    }
    message = to_contract_message(upstream, seq=1)
    _assert_valid(message)
    touch = message["touches"][0]
    assert set(touch.keys()) == {"id", "x", "y"}


def test_a_touch_missing_id_is_dropped():
    upstream = {
        "touches": [
            {"x": 0.1, "y": 0.2},  # no id
            {"id": 2, "x": 0.3, "y": 0.4},
        ]
    }
    message = to_contract_message(upstream, seq=1)
    _assert_valid(message)
    assert message["count"] == 1
    assert message["touches"] == [{"id": 2, "x": 0.3, "y": 0.4}]


def test_a_touch_missing_x_or_y_is_dropped():
    upstream = {
        "touches": [
            {"id": 1, "y": 0.2},  # no x
            {"id": 2, "x": 0.3},  # no y
            {"id": 3, "x": 0.5, "y": 0.6},
        ]
    }
    message = to_contract_message(upstream, seq=1)
    _assert_valid(message)
    assert message["count"] == 1
    assert message["touches"] == [{"id": 3, "x": 0.5, "y": 0.6}]


def test_a_touch_with_a_non_numeric_coordinate_is_dropped():
    upstream = {
        "touches": [
            {"id": 1, "x": "left", "y": 0.2},
            {"id": 2, "x": 0.3, "y": None},
            {"id": 3, "x": 0.7, "y": 0.8},
        ]
    }
    message = to_contract_message(upstream, seq=1)
    _assert_valid(message)
    assert message["count"] == 1
    assert message["touches"] == [{"id": 3, "x": 0.7, "y": 0.8}]


def test_a_touch_with_a_non_numeric_id_is_dropped():
    upstream = {
        "touches": [
            {"id": "abc", "x": 0.1, "y": 0.2},
            {"id": 2, "x": 0.3, "y": 0.4},
        ]
    }
    message = to_contract_message(upstream, seq=1)
    _assert_valid(message)
    assert message["count"] == 1
    assert message["touches"] == [{"id": 2, "x": 0.3, "y": 0.4}]


def test_a_touch_that_is_not_a_dict_is_dropped():
    upstream = {
        "touches": [
            [1, 0.1, 0.2],  # list, not a dict
            "touch",  # string, not a dict
            None,  # not a dict
            {"id": 9, "x": 0.5, "y": 0.5},
        ]
    }
    message = to_contract_message(upstream, seq=1)
    _assert_valid(message)
    assert message["count"] == 1
    assert message["touches"] == [{"id": 9, "x": 0.5, "y": 0.5}]


def test_a_frame_without_touches_yields_an_empty_message():
    message = to_contract_message({"seq": 5}, seq=1)
    _assert_valid(message)
    assert message == {"seq": 1, "count": 0, "touches": []}


def test_a_frame_whose_touches_is_not_a_list_yields_an_empty_message():
    for bad in ("not-a-list", {"id": 1}, 42, None):
        message = to_contract_message({"touches": bad}, seq=1)
        _assert_valid(message)
        assert message == {"seq": 1, "count": 0, "touches": []}


def test_all_touches_malformed_yields_a_valid_empty_message():
    upstream = {"touches": [{"x": 0.1}, "bad", None, {"id": "x", "x": 1, "y": 1}]}
    message = to_contract_message(upstream, seq=3)
    _assert_valid(message)
    assert message == {"seq": 3, "count": 0, "touches": []}
