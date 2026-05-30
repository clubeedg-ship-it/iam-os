"""Command-line entry point for the lidar-service.

Wires configuration, the LiDAR driver, the detection pipeline, and the frame
sink together under the connection manager, then runs until signalled:

    python -m iam_lidar [--simulate] [--config PATH] [--socket PATH]
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from iam_lidar.config import Config, ConfigError, load_config
from iam_lidar.connection import ConnectionManager
from iam_lidar.drivers.registry import create_driver
from iam_lidar.frames import Scan, TouchFrame
from iam_lidar.logging_setup import configure_logging
from iam_lidar.health import HealthReporter
from iam_lidar.output.frame_sink import FrameSink
from iam_lidar.output.status_writer import StatusSnapshot, StatusWriter
from iam_lidar.pipeline import Pipeline

_log = logging.getLogger("iam_lidar")

_DEFAULT_CONFIG = (
    Path(__file__).resolve().parent.parent / "config" / "lidar-service.toml"
)
# Touch frames are logged once every this many processed frames, so an
# operator watching the journal sees that tracking is alive without flooding.
_FRAME_LOG_INTERVAL = 30


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="iam_lidar", description="IAM-OS LiDAR service."
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_CONFIG, help="path to the TOML config"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="use the synthetic simulator driver (no hardware)",
    )
    parser.add_argument(
        "--socket", default=None, help="override the output socket path"
    )
    return parser.parse_args(argv)


def _build_sink(socket_path: str) -> FrameSink | None:
    """Start the frame sink; return None if its socket cannot be created."""
    sink = FrameSink(socket_path)
    try:
        sink.start()
    except OSError as exc:
        _log.warning("frame sink disabled: %s", exc)
        return None
    return sink


class _Service:
    """Holds the wired pipeline and sink, and handles each incoming scan."""

    def __init__(self, config: Config, sink: FrameSink | None) -> None:
        self._pipeline = Pipeline(config.detection)
        self._sink = sink
        self._frames = 0
        self._last_seq = 0
        self._last_seen_ts = 0.0
        self._active_preset = ""

    @property
    def pipeline(self) -> Pipeline:
        """The detection pipeline, for callers that install calibration."""
        return self._pipeline

    def on_scan(self, scan: Scan) -> None:
        """Capture the baseline from the first scan, then track touches."""
        if not self._pipeline.has_baseline:
            if self._pipeline.set_baseline(scan):
                _log.info("baseline captured")
            return
        frame = self._pipeline.process(scan)
        self._last_seq = frame.seq
        self._last_seen_ts = time.time()
        if self._sink is not None:
            self._sink.publish(frame)
        self._log_frame(frame)

    def reset_tracking(self) -> None:
        """Drop tracking continuity after a reconnect."""
        self._pipeline.reset_tracking()

    def snapshot(self) -> StatusSnapshot:
        """Sample the volatile fields for the status writer."""
        return StatusSnapshot(
            last_seq=self._last_seq,
            last_seen_ts=self._last_seen_ts,
            has_baseline=self._pipeline.has_baseline,
            active_preset=self._active_preset,
        )

    def _log_frame(self, frame: TouchFrame) -> None:
        self._frames += 1
        if frame.count and self._frames % _FRAME_LOG_INTERVAL == 0:
            touch = frame.touches[0]
            _log.info(
                "tracking %d touch(es): id=%d x=%.3f y=%.3f",
                frame.count,
                touch.id,
                touch.x,
                touch.y,
            )


def main(argv: list[str] | None = None) -> int:
    """Run the lidar-service. Returns a process exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    configure_logging(config.logging.level)

    driver_name = "simulator" if args.simulate else config.device.driver
    socket_path = args.socket or config.output.socket_path
    _log.info("starting lidar-service (driver=%s)", driver_name)

    sink = _build_sink(socket_path)
    service = _Service(config, sink)
    health = HealthReporter()
    status_writer = StatusWriter(
        path=config.status.file_path or None,
        health=health,
        snapshot=service.snapshot,
        heartbeat_interval_s=config.status.heartbeat_interval_s,
    )
    status_writer.attach()
    status_writer.start_heartbeat()
    manager = ConnectionManager(
        driver_factory=lambda: create_driver(driver_name, config.device),
        on_scan=service.on_scan,
        config=config.connection,
        health=health,
        on_connection_lost=service.reset_tracking,
    )

    def _shutdown(signum: int, _frame: object) -> None:
        _log.info("signal %d received, shutting down", signum)
        manager.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        manager.run()
    finally:
        status_writer.stop_heartbeat()
        status_writer.detach()
        if sink is not None:
            sink.close()
    _log.info("lidar-service stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
