"""Builds touch-contract messages (docs/touch-contract.md, specs.md §4.2).

The bridge re-stamps every message with its own monotonic sequence number,
recomputes the count, clamps coordinates, and keeps only contract fields — so
each message it emits conforms to the frozen contract regardless of what
arrives from upstream.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def _clamp_unit(value: object) -> float:
    """Coerce a value to a float clamped to the range [0.0, 1.0]."""
    return min(1.0, max(0.0, float(value)))  # type: ignore[arg-type]


def _coerce_touch(touch: object) -> dict | None:
    """Coerce one upstream touch into a contract touch, or ``None`` if invalid.

    A valid touch is a dict carrying numeric ``id``/``x``/``y``. Anything that
    is not a dict, is missing a required field, or has a non-numeric value is
    rejected so a malformed touch can be dropped instead of crashing the bridge.
    """
    if not isinstance(touch, dict):
        return None
    try:
        return {
            "id": int(touch["id"]),
            "x": _clamp_unit(touch["x"]),
            "y": _clamp_unit(touch["y"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def to_contract_message(frame: dict, seq: int) -> dict:
    """Build a contract message from an upstream lidar-service frame.

    This is the integration boundary between the platform and games, so it is
    defensive: a malformed upstream frame must never crash the bridge. Touches
    that are not dicts, are missing ``id``/``x``/``y``, or carry non-numeric
    values are dropped (and logged); ``count`` reflects only the valid touches
    actually included, keeping every emitted message schema-valid.

    Args:
        frame: an upstream frame; only its ``touches`` are used.
        seq: the bridge's monotonic sequence number for this message.
    """
    raw_touches = frame.get("touches", [])
    if not isinstance(raw_touches, list):
        _log.warning(
            "dropping seq=%d: upstream 'touches' is %s, expected a list",
            seq,
            type(raw_touches).__name__,
        )
        raw_touches = []

    touches: list[dict] = []
    dropped = 0
    for raw_touch in raw_touches:
        touch = _coerce_touch(raw_touch)
        if touch is None:
            dropped += 1
        else:
            touches.append(touch)
    if dropped:
        _log.warning("seq=%d: dropped %d malformed touch(es) from upstream", seq, dropped)

    return {"seq": seq, "count": len(touches), "touches": touches}


def empty_message(seq: int) -> dict:
    """Build a contract message with no touches.

    Sent on a heartbeat when upstream is silent, so consumers never see stale
    data (touch contract invariant 5).
    """
    return {"seq": seq, "count": 0, "touches": []}
