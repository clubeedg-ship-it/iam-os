"""Health state of the LiDAR connection (specs.md §6, R6).

The connection manager drives these states; the launcher reads them so an
operator can see whether tracking is live.
"""

from __future__ import annotations

import logging
from enum import Enum

_log = logging.getLogger(__name__)


class HealthState(Enum):
    """Lifecycle state of the LiDAR connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    STALE = "stale"
    FAILED = "failed"


class HealthReporter:
    """Holds the current health state and logs every transition."""

    def __init__(self) -> None:
        self._state = HealthState.DISCONNECTED

    @property
    def state(self) -> HealthState:
        """The current health state."""
        return self._state

    def set(self, state: HealthState) -> None:
        """Update the state, logging only when it actually changes."""
        if state is self._state:
            return
        previous = self._state
        self._state = state
        _log.info("health: %s -> %s", previous.value, state.value)
