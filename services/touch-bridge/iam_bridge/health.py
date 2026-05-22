"""Health state of the touch-bridge.

A minimal indicator of whether the bridge is receiving frames from
lidar-service. The launcher reads this in a later phase.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


class BridgeHealth:
    """Tracks whether the bridge is receiving frames from upstream."""

    def __init__(self) -> None:
        self._upstream_ok = False

    @property
    def upstream_ok(self) -> bool:
        """Whether the most recent broadcast came from a real upstream frame."""
        return self._upstream_ok

    def record_frame(self) -> None:
        """Note that a real upstream frame was received and broadcast."""
        if not self._upstream_ok:
            _log.info("upstream healthy: receiving frames")
            self._upstream_ok = True

    def record_silence(self) -> None:
        """Note that a heartbeat was broadcast because upstream was silent."""
        if self._upstream_ok:
            _log.warning("upstream silent: broadcasting heartbeat frames")
            self._upstream_ok = False
