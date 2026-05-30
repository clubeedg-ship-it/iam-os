"""Tests for web-server configuration loading."""

from pathlib import Path

import pytest

from iam_webserver.config import Config, ConfigError, load_config

_SAMPLE_TOML = """
[server]
host = "127.0.0.1"
port = 8080

[paths]
launcher_dist = "/usr/share/iam-os/launcher"
games_dir = "/usr/share/iam-os/games"

[lidar]
socket_path = "/run/iam-os/lidar.sock"
status_file = "/run/iam-os/lidar-status.json"
reconnect_initial_s = 0.5
reconnect_max_s = 5.0

[calibration]
presets_dir = "/var/lib/iam-os/calibration"
active_pointer_path = "/var/lib/iam-os/calibration/active.json"

[logging]
level = "INFO"
"""


def _write(tmp_path: Path, text: str = _SAMPLE_TOML) -> Path:
    path = tmp_path / "web-server.toml"
    path.write_text(text)
    return path


def test_loads_typed_values_from_file(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path))
    assert isinstance(config, Config)
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8080
    assert config.paths.launcher_dist == "/usr/share/iam-os/launcher"
    assert config.lidar.socket_path == "/run/iam-os/lidar.sock"
    assert config.calibration.presets_dir == "/var/lib/iam-os/calibration"
    assert config.logging.level == "INFO"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does-not-exist.toml")


def test_invalid_toml_raises(tmp_path: Path) -> None:
    path = tmp_path / "web-server.toml"
    path.write_text("not = valid = toml")
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_section_raises(tmp_path: Path) -> None:
    truncated = _SAMPLE_TOML.replace("[calibration]", "[unused]")
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, truncated))


def test_missing_value_raises(tmp_path: Path) -> None:
    truncated = _SAMPLE_TOML.replace("port = 8080\n", "")
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, truncated))


def test_zero_port_rejected(tmp_path: Path) -> None:
    bad = _SAMPLE_TOML.replace("port = 8080", "port = 0")
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, bad))


def test_invalid_log_level_rejected(tmp_path: Path) -> None:
    bad = _SAMPLE_TOML.replace('level = "INFO"', 'level = "LOUD"')
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, bad))


def test_empty_launcher_dist_rejected(tmp_path: Path) -> None:
    bad = _SAMPLE_TOML.replace(
        'launcher_dist = "/usr/share/iam-os/launcher"',
        'launcher_dist = ""',
    )
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, bad))


def test_reconnect_max_below_initial_rejected(tmp_path: Path) -> None:
    bad = _SAMPLE_TOML.replace(
        "reconnect_initial_s = 0.5\nreconnect_max_s = 5.0",
        "reconnect_initial_s = 5.0\nreconnect_max_s = 1.0",
    )
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, bad))
