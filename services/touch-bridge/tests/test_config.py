"""Tests for typed configuration loading and validation."""

from pathlib import Path

import pytest

from iam_bridge.config import Config, ConfigError, load_config

_SAMPLE_TOML = """
[upstream]
socket_path = "/run/iam-os/lidar.sock"

[server]
host = "127.0.0.1"
port = 8765

[broadcast]
heartbeat_interval_s = 1.0

[logging]
level = "INFO"
"""


def _write(tmp_path, text=_SAMPLE_TOML):
    path = tmp_path / "touch-bridge.toml"
    path.write_text(text)
    return path


def test_loads_typed_values_from_file(tmp_path):
    config = load_config(_write(tmp_path))
    assert config.upstream.socket_path == "/run/iam-os/lidar.sock"
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8765
    assert config.broadcast.heartbeat_interval_s == 1.0
    assert config.logging.level == "INFO"


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does-not-exist.toml")


def test_missing_section_raises_config_error(tmp_path):
    incomplete = _SAMPLE_TOML.replace('[logging]\nlevel = "INFO"', "")
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, incomplete))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('socket_path = "/run/iam-os/lidar.sock"', 'socket_path = ""'),
        ('host = "127.0.0.1"', 'host = ""'),
        ("port = 8765", "port = 0"),
        ("port = 8765", "port = 70000"),
        ("port = 8765", "port = -1"),
        ("heartbeat_interval_s = 1.0", "heartbeat_interval_s = 0.0"),
        ("heartbeat_interval_s = 1.0", "heartbeat_interval_s = -1.0"),
        ('level = "INFO"', 'level = "VERBOSE"'),
    ],
)
def test_invalid_value_raises_config_error(tmp_path, old, new):
    broken = _SAMPLE_TOML.replace(old, new)
    assert broken != _SAMPLE_TOML
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, broken))


def test_shipped_config_file_is_valid():
    shipped = Path(__file__).parents[1] / "config" / "touch-bridge.toml"
    config = load_config(shipped)
    assert isinstance(config, Config)
    assert 1 <= config.server.port <= 65535
