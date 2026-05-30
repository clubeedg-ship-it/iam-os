"""Typed configuration for the web-server.

Loads ``config/web-server.toml`` into frozen, typed dataclasses. Mirrors the
loader pattern in lidar-service and touch-bridge.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Raised when configuration is missing, unreadable, or incomplete."""


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def _require_positive(value: float, label: str) -> None:
    if value <= 0:
        raise ConfigError(f"{label} must be > 0, got {value}")


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Where the HTTP server listens."""

    host: str
    port: int

    def __post_init__(self) -> None:
        if not (0 < self.port < 65536):
            raise ConfigError(f"[server].port must be 1-65535, got {self.port}")


@dataclass(frozen=True, slots=True)
class PathsConfig:
    """Filesystem locations the web-server serves and writes to."""

    launcher_dist: str
    games_dir: str

    def __post_init__(self) -> None:
        if not self.launcher_dist:
            raise ConfigError("[paths].launcher_dist must not be empty")
        if not self.games_dir:
            raise ConfigError("[paths].games_dir must not be empty")


@dataclass(frozen=True, slots=True)
class LidarConfig:
    """How the web-server reaches the lidar-service.

    The socket is read as a client of lidar-service's frame sink (carrying
    raw mm fields the bridge strips). The status file is the JSON document
    lidar-service writes; the web-server reads it for /api/status.
    """

    socket_path: str
    status_file: str
    reconnect_initial_s: float
    reconnect_max_s: float

    def __post_init__(self) -> None:
        if not self.socket_path:
            raise ConfigError("[lidar].socket_path must not be empty")
        if not self.status_file:
            raise ConfigError("[lidar].status_file must not be empty")
        _require_positive(self.reconnect_initial_s, "[lidar].reconnect_initial_s")
        _require_positive(self.reconnect_max_s, "[lidar].reconnect_max_s")
        if self.reconnect_max_s < self.reconnect_initial_s:
            raise ConfigError(
                "[lidar].reconnect_max_s must be >= reconnect_initial_s, got "
                f"{self.reconnect_max_s} < {self.reconnect_initial_s}"
            )


@dataclass(frozen=True, slots=True)
class CalibrationConfig:
    """The calibration preset store the web-server owns.

    The web-server writes preset files and the active pointer here.
    lidar-service polls the active pointer at the same paths and reloads
    on change. Both services must agree on the paths.
    """

    presets_dir: str
    active_pointer_path: str

    def __post_init__(self) -> None:
        if not self.presets_dir:
            raise ConfigError("[calibration].presets_dir must not be empty")
        if not self.active_pointer_path:
            raise ConfigError("[calibration].active_pointer_path must not be empty")


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Logging behaviour."""

    level: str

    def __post_init__(self) -> None:
        if self.level not in _LOG_LEVELS:
            raise ConfigError(
                f"[logging].level must be one of {', '.join(_LOG_LEVELS)}, "
                f"got {self.level!r}"
            )


@dataclass(frozen=True, slots=True)
class Config:
    """The complete web-server configuration."""

    server: ServerConfig
    paths: PathsConfig
    lidar: LidarConfig
    calibration: CalibrationConfig
    logging: LoggingConfig


def load_config(path: str | Path) -> Config:
    """Load web-server configuration from a TOML file.

    Raises:
        ConfigError: if the file is missing, is not valid TOML, or omits a
            required section or value.
    """
    config_path = Path(path)
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {config_path}: {exc}") from exc

    try:
        return Config(
            server=ServerConfig(**data["server"]),
            paths=PathsConfig(**data["paths"]),
            lidar=LidarConfig(**data["lidar"]),
            calibration=CalibrationConfig(**data["calibration"]),
            logging=LoggingConfig(**data["logging"]),
        )
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"invalid configuration in {config_path}: {exc}") from exc
