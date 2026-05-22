"""Touch tracking: assigns stable ids to detected touches across frames.

A touch close to one in the previous frame inherits that touch's id, so a
consumer can follow a single physical touch over time. A touch with no nearby
predecessor receives a fresh id. Ids are never recycled.
"""

from __future__ import annotations

import math

from iam_lidar.frames import Touch, TouchCandidate


class Tracker:
    """Stateful, per-frame id assignment."""

    def __init__(self, *, tolerance_mm: float) -> None:
        self._tolerance_mm = tolerance_mm
        self._previous: list[Touch] = []
        self._next_id = 1

    def reset(self) -> None:
        """Forget the previous frame.

        Use this after a gap in scan data: continuity is lost, so the next
        frame's touches all count as new. The id counter is not rewound — ids
        stay globally unique for the lifetime of the tracker.
        """
        self._previous = []

    def assign_ids(self, candidates: list[TouchCandidate]) -> list[Touch]:
        """Turn candidates into identified touches.

        Each candidate is matched to the nearest unclaimed touch from the
        previous frame within ``tolerance_mm`` and inherits its id. An
        unmatched candidate receives a fresh id. Candidates are processed in
        order, and each previous id is reused at most once.
        """
        touches: list[Touch] = []
        claimed: set[int] = set()

        for candidate in candidates:
            matched_id = self._nearest_previous_id(candidate, claimed)
            if matched_id is None:
                matched_id = self._next_id
                self._next_id += 1
            else:
                claimed.add(matched_id)
            touches.append(
                Touch(
                    id=matched_id,
                    x=candidate.x,
                    y=candidate.y,
                    raw_x_mm=candidate.raw_x_mm,
                    raw_y_mm=candidate.raw_y_mm,
                    size=candidate.size,
                )
            )

        self._previous = touches
        return touches

    def _nearest_previous_id(
        self, candidate: TouchCandidate, claimed: set[int]
    ) -> int | None:
        """Return the id of the nearest unclaimed previous touch within tolerance."""
        best_id: int | None = None
        best_distance = self._tolerance_mm
        for previous in self._previous:
            if previous.id in claimed:
                continue
            distance = math.hypot(
                candidate.raw_x_mm - previous.raw_x_mm,
                candidate.raw_y_mm - previous.raw_y_mm,
            )
            if distance < best_distance:
                best_distance = distance
                best_id = previous.id
        return best_id
