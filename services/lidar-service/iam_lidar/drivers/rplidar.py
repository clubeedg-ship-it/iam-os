"""RPLIDAR driver — drives Slamtec RPLIDAR sensors over a USB serial link.

This is the production driver. It cannot be exercised without hardware, so it
is validated on a real sensor during field validation (specs.md §13, Phase 8);
the simulator driver covers the automated test path.

``pyrplidar`` and ``pyserial`` are imported lazily so the package — and its
test suite — work without those libraries installed.
"""

from __future__ import annotations

import time

from iam_lidar.drivers.base import DeviceInfo, LidarDriver, LidarError
from iam_lidar.frames import Scan, ScanSample

# read_scan accumulates samples for roughly one revolution, then returns.
_SCAN_DURATION_S = 0.1
# Hard cap on samples per scan, so read_scan always returns even if the
# device streams without pause.
_SCAN_SAMPLE_CAP = 4000


def find_serial_port(keywords: list[str]) -> str | None:
    """Return the first serial port whose description matches any keyword.

    Used to auto-detect the LiDAR's USB adapter (specs.md §6, R2). Returns
    ``None`` if pyserial is unavailable or no matching port is found.
    """
    try:
        import serial.tools.list_ports
    except ImportError:
        return None
    for port in serial.tools.list_ports.comports():
        description = f"{port.description} {port.manufacturer or ''}".lower()
        if any(keyword.lower() in description for keyword in keywords):
            return port.device
    return None


class RpLidarDriver(LidarDriver):
    """Driver for Slamtec RPLIDAR sensors (the S2 / S2E / C1 family)."""

    def __init__(
        self,
        *,
        port: str,
        baud_rates: list[int],
        adapter_keywords: list[str],
        connect_timeout_s: float,
    ) -> None:
        self._configured_port = port
        self._baud_rates = baud_rates
        self._adapter_keywords = adapter_keywords
        self._connect_timeout_s = connect_timeout_s
        self._lidar: object | None = None
        self._scan_generator = None

    def connect(self) -> DeviceInfo:
        port = self._configured_port or find_serial_port(self._adapter_keywords)
        if not port:
            raise LidarError("no LiDAR serial port found")
        try:
            from pyrplidar import PyRPlidar
        except ImportError as exc:
            raise LidarError("pyrplidar is not installed") from exc

        last_error: Exception | None = None
        for baud in self._baud_rates:
            lidar = PyRPlidar()
            try:
                lidar.connect(port, baud, timeout=self._connect_timeout_s)
                lidar.set_motor_pwm(500)
                time.sleep(self._connect_timeout_s)
                info = lidar.get_info()
                self._lidar = lidar
                self._scan_generator = lidar.start_scan()()
                return DeviceInfo(model="RPLIDAR", detail=f"{port}@{baud} {info}")
            except Exception as exc:  # pyrplidar raises a range of error types
                last_error = exc
                self._safe_close(lidar)
        raise LidarError(f"could not connect on {port}: {last_error}")

    def read_scan(self) -> Scan:
        if self._scan_generator is None:
            raise LidarError("RPLIDAR is not connected")
        scan: Scan = []
        deadline = time.monotonic() + _SCAN_DURATION_S
        try:
            for measurement in self._scan_generator:
                distance = float(measurement.distance)
                if distance > 0.0:
                    scan.append(
                        ScanSample(
                            angle_deg=float(measurement.angle),
                            distance_mm=distance,
                        )
                    )
                if time.monotonic() >= deadline or len(scan) >= _SCAN_SAMPLE_CAP:
                    break
        except Exception as exc:  # convert any device failure to the contract error
            raise LidarError(f"scan read failed: {exc}") from exc
        if not scan:
            raise LidarError("RPLIDAR returned no samples")
        return scan

    def disconnect(self) -> None:
        self._scan_generator = None
        self._safe_close(self._lidar)
        self._lidar = None

    @staticmethod
    def _safe_close(lidar: object | None) -> None:
        """Best-effort device shutdown; errors during cleanup are ignored."""
        if lidar is None:
            return
        for method in ("stop", "set_motor_pwm", "disconnect"):
            try:
                attr = getattr(lidar, method)
                attr(0) if method == "set_motor_pwm" else attr()
            except Exception:  # noqa: S110 - cleanup must not raise
                pass
