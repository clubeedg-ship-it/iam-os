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
    upstream = {"touches": [{"id": 1, "x": 0.5, "y": 0.5, "raw_x_mm": 100.0, "size": 12}]}
    touch = to_contract_message(upstream, seq=1)["touches"][0]
    assert set(touch.keys()) == {"id", "x", "y"}
