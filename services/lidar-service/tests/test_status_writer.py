"""Tests for the status-file writer."""

import json
import time
from pathlib import Path

from iam_lidar.health import HealthReporter, HealthState
from iam_lidar.output.status_writer import StatusSnapshot, StatusWriter


def _snapshot(**overrides) -> StatusSnapshot:
    defaults = dict(
        last_seq=0,
        last_seen_ts=0.0,
        has_baseline=False,
        active_preset="",
    )
    defaults.update(overrides)
    return StatusSnapshot(**defaults)


def test_write_now_serialises_health_and_snapshot(tmp_path: Path) -> None:
    health = HealthReporter()
    health.set(HealthState.STREAMING)
    snapshot_path = tmp_path / "lidar-status.json"
    writer = StatusWriter(
        path=snapshot_path,
        health=health,
        snapshot=lambda: _snapshot(
            last_seq=42, last_seen_ts=1.5, has_baseline=True, active_preset="default"
        ),
    )
    writer.write_now()

    payload = json.loads(snapshot_path.read_text())
    assert payload["state"] == "streaming"
    assert payload["last_seq"] == 42
    assert payload["last_seen_ts"] == 1.5
    assert payload["has_baseline"] is True
    assert payload["active_preset"] == "default"
    assert "updated_at" in payload


def test_write_now_is_atomic_no_tmp_file_remains(tmp_path: Path) -> None:
    writer = StatusWriter(
        path=tmp_path / "lidar-status.json",
        health=HealthReporter(),
        snapshot=_snapshot,
    )
    writer.write_now()
    leftover = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftover == []


def test_write_now_creates_missing_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deep" / "lidar-status.json"
    writer = StatusWriter(
        path=target, health=HealthReporter(), snapshot=_snapshot
    )
    writer.write_now()
    assert target.is_file()


def test_disabled_writer_does_nothing(tmp_path: Path) -> None:
    """An empty/None path means status reporting is disabled."""
    writer = StatusWriter(path=None, health=HealthReporter(), snapshot=_snapshot)
    writer.write_now()  # must not raise
    assert list(tmp_path.iterdir()) == []


def test_health_transition_triggers_a_write(tmp_path: Path) -> None:
    """When the connection manager flips the health state, the status file
    must reflect it without waiting for the next heartbeat — the launcher
    should see a fresh state immediately after a transition.
    """
    target = tmp_path / "lidar-status.json"
    health = HealthReporter()
    writer = StatusWriter(path=target, health=health, snapshot=_snapshot)
    writer.attach()  # registers the listener
    try:
        health.set(HealthState.CONNECTING)
        payload = json.loads(target.read_text())
        assert payload["state"] == "connecting"

        health.set(HealthState.STREAMING)
        payload = json.loads(target.read_text())
        assert payload["state"] == "streaming"
    finally:
        writer.detach()


def test_heartbeat_thread_writes_periodically(tmp_path: Path) -> None:
    target = tmp_path / "lidar-status.json"
    writer = StatusWriter(
        path=target,
        health=HealthReporter(),
        snapshot=_snapshot,
        heartbeat_interval_s=0.05,
    )
    writer.start_heartbeat()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not target.exists():
            time.sleep(0.01)
        assert target.is_file()
        first_mtime = target.stat().st_mtime
        # Wait long enough for at least one more heartbeat.
        time.sleep(0.15)
        assert target.stat().st_mtime >= first_mtime
    finally:
        writer.stop_heartbeat()


def test_stop_heartbeat_terminates_thread(tmp_path: Path) -> None:
    writer = StatusWriter(
        path=tmp_path / "lidar-status.json",
        health=HealthReporter(),
        snapshot=_snapshot,
        heartbeat_interval_s=0.05,
    )
    writer.start_heartbeat()
    writer.stop_heartbeat()
    # A second stop is a no-op.
    writer.stop_heartbeat()
