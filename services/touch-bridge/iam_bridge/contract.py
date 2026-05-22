"""Builds touch-contract messages (docs/touch-contract.md, specs.md §4.2).

The bridge re-stamps every message with its own monotonic sequence number,
recomputes the count, clamps coordinates, and keeps only contract fields — so
each message it emits conforms to the frozen contract regardless of what
arrives from upstream.
"""

from __future__ import annotations


def _clamp_unit(value: object) -> float:
    """Coerce a value to a float clamped to the range [0.0, 1.0]."""
    return min(1.0, max(0.0, float(value)))  # type: ignore[arg-type]


def to_contract_message(frame: dict, seq: int) -> dict:
    """Build a contract message from an upstream lidar-service frame.

    Args:
        frame: an upstream frame; only its ``touches`` are used.
        seq: the bridge's monotonic sequence number for this message.
    """
    touches = [
        {
            "id": int(touch["id"]),
            "x": _clamp_unit(touch["x"]),
            "y": _clamp_unit(touch["y"]),
        }
        for touch in frame.get("touches", [])
    ]
    return {"seq": seq, "count": len(touches), "touches": touches}


def empty_message(seq: int) -> dict:
    """Build a contract message with no touches.

    Sent on a heartbeat when upstream is silent, so consumers never see stale
    data (touch contract invariant 5).
    """
    return {"seq": seq, "count": 0, "touches": []}
