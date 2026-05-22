"""Tests for typed configuration loading and environment overrides."""

from pathlib import Path

import pytest

from iam_lidar.config import Config, ConfigError, load_config

_SAMPLE_TOML = """
[device]
driver = "rplidar"
port = ""
baud_rates = [1000000, 256000, 115200]
adapter_keywords = ["CP210", "Silicon"]
connect_timeout_s = 3.0

[connection]
backoff_initial_s = 0.5
backoff_max_s = 30.0
backoff_factor = 2.0
watchdog_timeout_s = 3.0

[detection]
distance_min_mm = 200
distance_max_mm = 6000
baseline_threshold_mm = 150
baseline_min_points = 10
cluster_tolerance_mm = 100
cluster_min_points = 8
cluster_max_points = 300
track_tolerance_mm = 150

[output]
socket_path = "/run/iam-os/lidar.sock"

[logging]
level = "INFO"
"""


def _write(tmp_path, text=_SAMPLE_TOML):
    path = tmp_path / "lidar-service.toml"
    path.write_text(text)
    return path


def test_loads_typed_values_from_file(tmp_path):
    config = load_config(_write(tmp_path), env={})
    assert config.device.driver == "rplidar"
    assert config.device.baud_rates == [1000000, 256000, 115200]
    assert config.detection.cluster_min_points == 8
    assert config.connection.watchdog_timeout_s == 3.0


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does-not-exist.toml", env={})


def test_missing_value_raises_config_error(tmp_path):
    incomplete = _SAMPLE_TOML.replace('level = "INFO"', "")
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, incomplete), env={})


def test_environment_overrides_a_scalar_value(tmp_path):
    config = load_config(
        _write(tmp_path), env={"IAM_LIDAR_DEVICE_PORT": "/dev/ttyUSB0"}
    )
    assert config.device.port == "/dev/ttyUSB0"


def test_environment_override_is_coerced_to_the_field_type(tmp_path):
    config = load_config(
        _write(tmp_path), env={"IAM_LIDAR_DETECTION_CLUSTER_MIN_POINTS": "12"}
    )
    assert config.detection.cluster_min_points == 12
    assert isinstance(config.detection.cluster_min_points, int)


def test_environment_override_of_a_list(tmp_path):
    config = load_config(
        _write(tmp_path), env={"IAM_LIDAR_DEVICE_BAUD_RATES": "115200, 9600"}
    )
    assert config.device.baud_rates == [115200, 9600]


def test_shipped_config_file_is_valid():
    shipped = Path(__file__).parents[1] / "config" / "lidar-service.toml"
    config = load_config(shipped, env={})
    assert isinstance(config, Config)
    assert config.device.driver in ("rplidar", "simulator")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("connect_timeout_s = 3.0", "connect_timeout_s = -1.0"),
        ("backoff_initial_s = 0.5", "backoff_initial_s = 0.0"),
        ("backoff_max_s = 30.0", "backoff_max_s = -5.0"),
        ("watchdog_timeout_s = 3.0", "watchdog_timeout_s = -2.0"),
        ("backoff_factor = 2.0", "backoff_factor = 0.5"),
        ("backoff_max_s = 30.0", "backoff_max_s = 0.1"),
        ("baud_rates = [1000000, 256000, 115200]", "baud_rates = []"),
        ("distance_min_mm = 200", "distance_min_mm = 0"),
        ("distance_min_mm = 200", "distance_min_mm = 9000"),
        ("baseline_threshold_mm = 150", "baseline_threshold_mm = -1"),
        ("cluster_tolerance_mm = 100", "cluster_tolerance_mm = 0"),
        ("track_tolerance_mm = 150", "track_tolerance_mm = -3"),
        ("baseline_min_points = 10", "baseline_min_points = 0"),
        ("cluster_min_points = 8", "cluster_min_points = 0"),
        ("cluster_min_points = 8", "cluster_min_points = 400"),
        ('socket_path = "/run/iam-os/lidar.sock"', 'socket_path = ""'),
        ('level = "INFO"', 'level = "VERBOSE"'),
    ],
)
def test_invalid_value_raises_config_error(tmp_path, old, new):
    broken = _SAMPLE_TOML.replace(old, new)
    assert broken != _SAMPLE_TOML
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, broken), env={})


def test_invalid_value_from_environment_override_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(
            _write(tmp_path),
            env={"IAM_LIDAR_CONNECTION_WATCHDOG_TIMEOUT_S": "-1.0"},
        )
