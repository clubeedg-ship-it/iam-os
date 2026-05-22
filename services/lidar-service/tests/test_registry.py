"""Tests for the driver registry."""

import pytest

from iam_lidar.config import DeviceConfig
from iam_lidar.drivers.registry import create_driver
from iam_lidar.drivers.rplidar import RpLidarDriver
from iam_lidar.simulator import SimDriver

_DEVICE = DeviceConfig(
    driver="simulator",
    port="",
    baud_rates=[115200],
    adapter_keywords=["CP210"],
    connect_timeout_s=3.0,
)


def test_creates_the_simulator_driver():
    assert isinstance(create_driver("simulator", _DEVICE), SimDriver)


def test_creates_the_rplidar_driver():
    assert isinstance(create_driver("rplidar", _DEVICE), RpLidarDriver)


def test_unknown_driver_name_raises():
    with pytest.raises(ValueError):
        create_driver("nonsense", _DEVICE)
