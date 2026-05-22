"""Tests for the simulator driver — synthetic scans, no hardware."""

import pytest

from iam_lidar.drivers.base import DeviceInfo, LidarDriver, LidarError
from iam_lidar.frames import ScanSample
from iam_lidar.simulator import SimDriver


def test_sim_driver_implements_the_lidar_driver_interface():
    assert isinstance(SimDriver(), LidarDriver)


def test_connect_returns_device_info():
    info = SimDriver().connect()
    assert isinstance(info, DeviceInfo)
    assert info.model == "simulator"


def test_read_scan_before_connect_raises():
    with pytest.raises(LidarError):
        SimDriver().read_scan()


def test_read_scan_after_connect_returns_a_full_scan():
    driver = SimDriver()
    driver.connect()
    scan = driver.read_scan()
    assert len(scan) >= 360
    assert all(isinstance(sample, ScanSample) for sample in scan)
    assert all(sample.distance_mm > 0 for sample in scan)


def test_successive_scans_differ_as_the_simulated_object_moves():
    driver = SimDriver()
    driver.connect()
    first = driver.read_scan()
    later = first
    for _ in range(20):
        later = driver.read_scan()
    assert [s.distance_mm for s in first] != [s.distance_mm for s in later]


def test_read_scan_after_disconnect_raises():
    driver = SimDriver()
    driver.connect()
    driver.disconnect()
    with pytest.raises(LidarError):
        driver.read_scan()
