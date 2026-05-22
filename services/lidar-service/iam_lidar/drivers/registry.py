"""Maps the configured driver name to a concrete :class:`LidarDriver`."""

from __future__ import annotations

from iam_lidar.config import DeviceConfig
from iam_lidar.drivers.base import LidarDriver
from iam_lidar.drivers.rplidar import RpLidarDriver
from iam_lidar.simulator import SimDriver


def create_driver(name: str, device: DeviceConfig) -> LidarDriver:
    """Create the driver named in configuration.

    Args:
        name: the driver name — ``"rplidar"`` or ``"simulator"``.
        device: device configuration, passed to drivers that need it.

    Raises:
        ValueError: if ``name`` is not a known driver.
    """
    if name == "simulator":
        return SimDriver()
    if name == "rplidar":
        return RpLidarDriver(
            port=device.port,
            baud_rates=device.baud_rates,
            adapter_keywords=device.adapter_keywords,
            connect_timeout_s=device.connect_timeout_s,
        )
    raise ValueError(f"unknown driver: {name!r}")
