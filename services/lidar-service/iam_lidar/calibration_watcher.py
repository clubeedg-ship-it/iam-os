"""Watches the active calibration preset and reloads it on change.

The launcher's web-server owns the preset store: it writes preset files and
an ``active.json`` pointer that names the selected preset. The watcher polls
the pointer's mtime, loads the named preset, and hands a fresh
:class:`Calibration` to the lidar-service pipeline through a callback. The
running service picks up a new calibration without a restart.

Files are read-only here — the launcher is the writer. Atomic helpers are
provided so the web-server (or tests) can produce files this watcher will
read consistently.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

from iam_lidar.detection.calibration import Calibration

_log = logging.getLogger(__name__)

OnChange = Callable[["Calibration | None", str], None]


def write_active_pointer(path: Path, name: str) -> None:
    """Atomically write the active-preset pointer file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"name": name}))
    os.replace(tmp, path)


def write_preset(presets_dir: Path, preset: dict) -> Path:
    """Atomically write a preset document into ``presets_dir``.

    The file is named ``<preset['name']>.json``. Returns the written path.
    """
    presets_dir.mkdir(parents=True, exist_ok=True)
    path = presets_dir / f"{preset['name']}.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(preset))
    os.replace(tmp, path)
    return path


def _parse_corners(raw: object, label: str) -> list[tuple[float, float]]:
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError(f"{label} must be a list of 4 [x, y] points")
    corners: list[tuple[float, float]] = []
    for point in raw:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError(f"{label} entries must be [x, y] pairs")
        corners.append((float(point[0]), float(point[1])))
    return corners


def _load_preset(path: Path) -> Calibration:
    """Read a preset file and return its Calibration, or raise."""
    data = json.loads(path.read_text())
    source = _parse_corners(data.get("source_corners"), "source_corners")
    dest_raw = data.get("dest_corners")
    dest = _parse_corners(dest_raw, "dest_corners") if dest_raw is not None else None
    return Calibration.from_corners(source, dest)


class CalibrationWatcher:
    """Polls the active-preset pointer and reloads when it changes."""

    def __init__(
        self,
        *,
        presets_dir: Path | str,
        active_pointer_path: Path | str,
        on_change: OnChange,
        poll_interval_s: float = 0.5,
    ) -> None:
        self._presets_dir = Path(presets_dir)
        self._active_pointer_path = Path(active_pointer_path)
        self._on_change = on_change
        self._poll_interval_s = poll_interval_s
        self._current_name = ""
        self._last_mtime_ns = -1
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def current_name(self) -> str:
        """The name of the currently-installed preset, or ``""`` if none."""
        return self._current_name

    def start(self) -> None:
        """Begin polling on a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="calibration-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop polling; safe to call repeatedly."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def load_once(self) -> None:
        """Force one load attempt regardless of the polled mtime."""
        self._last_mtime_ns = -1
        self.poll()

    def poll(self) -> None:
        """Re-evaluate the pointer; reload if it changed since the last poll.

        Returns silently when the pointer is missing, points at a missing
        preset, or names a preset that fails to parse — none of those should
        crash the service.
        """
        try:
            mtime_ns = self._active_pointer_path.stat().st_mtime_ns
        except FileNotFoundError:
            return
        if mtime_ns == self._last_mtime_ns:
            return
        self._last_mtime_ns = mtime_ns

        try:
            pointer = json.loads(self._active_pointer_path.read_text())
            name = str(pointer["name"])
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
            _log.warning("calibration: ignoring malformed active pointer: %s", exc)
            return

        if not name:
            return

        preset_path = self._presets_dir / f"{name}.json"
        try:
            calibration = _load_preset(preset_path)
        except FileNotFoundError:
            _log.warning(
                "calibration: active preset %r not found at %s", name, preset_path
            )
            return
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            _log.warning("calibration: failed to load preset %r: %s", name, exc)
            return

        self._current_name = name
        _log.info("calibration: installed preset %r", name)
        self._on_change(calibration, name)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.poll()
            self._stop.wait(self._poll_interval_s)
