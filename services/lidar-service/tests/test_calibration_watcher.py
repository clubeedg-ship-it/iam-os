"""Tests for the calibration watcher.

The watcher polls an active-pointer file on disk; when it changes, it loads
the named preset and hands a fresh :class:`Calibration` to the pipeline.
This is how the launcher's web-server pushes a new calibration into the
running lidar-service without a restart.
"""

import json
import time
from pathlib import Path

import pytest

from iam_lidar.calibration_watcher import (
    CalibrationWatcher,
    write_active_pointer,
    write_preset,
)
from iam_lidar.detection.calibration import Calibration


def _square_preset(name: str = "default") -> dict:
    return {
        "name": name,
        "source_corners": [[0.0, 0.0], [1000.0, 0.0], [1000.0, 1000.0], [0.0, 1000.0]],
        "dest_corners": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    }


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[Calibration | None, str]] = []

    def __call__(self, calibration: Calibration | None, name: str) -> None:
        self.calls.append((calibration, name))


def test_cold_load_installs_calibration_from_active_preset(tmp_path: Path) -> None:
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    write_preset(presets_dir, _square_preset("default"))
    active = tmp_path / "active.json"
    write_active_pointer(active, "default")

    recorder = _Recorder()
    watcher = CalibrationWatcher(
        presets_dir=presets_dir,
        active_pointer_path=active,
        on_change=recorder,
    )
    watcher.load_once()

    assert len(recorder.calls) == 1
    calibration, name = recorder.calls[0]
    assert name == "default"
    assert calibration is not None
    # 0..1000 mm in the source maps onto the unit square.
    assert calibration.map_point(500.0, 500.0) == pytest.approx((0.5, 0.5))


def test_no_active_pointer_yields_no_calibration(tmp_path: Path) -> None:
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    recorder = _Recorder()
    watcher = CalibrationWatcher(
        presets_dir=presets_dir,
        active_pointer_path=tmp_path / "active.json",
        on_change=recorder,
    )
    watcher.load_once()

    # No active pointer = nothing to load; the callback is never invoked.
    assert recorder.calls == []
    assert watcher.current_name == ""


def test_missing_preset_named_in_pointer_is_handled(tmp_path: Path) -> None:
    """A pointer to a preset that does not exist must not crash the service."""
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    active = tmp_path / "active.json"
    write_active_pointer(active, "ghost")

    recorder = _Recorder()
    watcher = CalibrationWatcher(
        presets_dir=presets_dir,
        active_pointer_path=active,
        on_change=recorder,
    )
    watcher.load_once()

    assert recorder.calls == []
    assert watcher.current_name == ""


def test_malformed_preset_is_skipped(tmp_path: Path) -> None:
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    (presets_dir / "broken.json").write_text("not json")
    active = tmp_path / "active.json"
    write_active_pointer(active, "broken")

    recorder = _Recorder()
    watcher = CalibrationWatcher(
        presets_dir=presets_dir,
        active_pointer_path=active,
        on_change=recorder,
    )
    watcher.load_once()

    assert recorder.calls == []


def test_pointer_change_triggers_reload(tmp_path: Path) -> None:
    """Switching the active pointer to a new preset reloads the calibration."""
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    write_preset(presets_dir, _square_preset("a"))
    write_preset(presets_dir, _square_preset("b"))
    active = tmp_path / "active.json"
    write_active_pointer(active, "a")

    recorder = _Recorder()
    watcher = CalibrationWatcher(
        presets_dir=presets_dir,
        active_pointer_path=active,
        on_change=recorder,
        poll_interval_s=0.05,
    )
    watcher.load_once()
    assert watcher.current_name == "a"

    write_active_pointer(active, "b")
    # Force the watcher to re-evaluate (don't depend on the thread here).
    watcher.poll()
    assert watcher.current_name == "b"
    assert [name for _, name in recorder.calls] == ["a", "b"]


def test_polling_thread_reloads_on_change(tmp_path: Path) -> None:
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    write_preset(presets_dir, _square_preset("a"))
    write_preset(presets_dir, _square_preset("b"))
    active = tmp_path / "active.json"
    write_active_pointer(active, "a")

    recorder = _Recorder()
    watcher = CalibrationWatcher(
        presets_dir=presets_dir,
        active_pointer_path=active,
        on_change=recorder,
        poll_interval_s=0.05,
    )
    watcher.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and watcher.current_name != "a":
            time.sleep(0.02)
        assert watcher.current_name == "a"

        write_active_pointer(active, "b")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and watcher.current_name != "b":
            time.sleep(0.02)
        assert watcher.current_name == "b"
    finally:
        watcher.stop()


def test_stop_is_idempotent(tmp_path: Path) -> None:
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    watcher = CalibrationWatcher(
        presets_dir=presets_dir,
        active_pointer_path=tmp_path / "active.json",
        on_change=_Recorder(),
        poll_interval_s=0.05,
    )
    watcher.start()
    watcher.stop()
    watcher.stop()  # must not raise


def test_write_preset_round_trip(tmp_path: Path) -> None:
    """Helper: writing then reading a preset preserves the document."""
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    payload = _square_preset("default")
    path = write_preset(presets_dir, payload)
    assert json.loads(path.read_text()) == payload
