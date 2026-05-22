"""Typed configuration for the touch-bridge.

Loads ``config/touch-bridge.toml`` into frozen, typed dataclasses. Common
overrides (the upstream socket and the server port) are also exposed as
command-line flags on the entry point.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Raised when configuration is missing, unreadable, or incomplete."""


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True, slots=True)
class UpstreamConfig:
    """The lidar-service socket the bridge reads frames from."""

    socket_path: str

    def __post_init__(self) -> None:
        """Reject an empty upstream socket path."""
        if not self.socket_path:
            raise ConfigError("[upstream].socket_path must not be empty")


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """The WebSocket address the bridge serves on."""

    host: str
    port: int

    def __post_init__(self) -> None:
        """Reject an empty host or an out-of-range port."""
        if not self.host:
            raise ConfigError("[server].host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ConfigError(
                f"[server].port must be in 1..65535, got {self.port}"
            )


@dataclass(frozen=True, slots=True)
class BroadcastConfig:
    """How often an empty frame is sent when upstream is silent."""

    heartbeat_interval_s: float

    def __post_init__(self) -> None:
        """Reject a non-positive heartbeat interval."""
        if self.heartbeat_interval_s <= 0:
            raise ConfigError(
                "[broadcast].heartbeat_interval_s must be > 0, got "
                f"{self.heartbeat_interval_s}"
            )


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Logging behaviour."""

    level: str

    def __post_init__(self) -> None:
        """Reject an unknown log level."""
        if self.level not in _LOG_LEVELS:
            raise ConfigError(
                f"[logging].level must be one of {', '.join(_LOG_LEVELS)}, "
                f"got {self.level!r}"
            )


@dataclass(frozen=True, slots=True)
class Config:
    """The complete touch-bridge configuration."""

    upstream: UpstreamConfig
    server: ServerConfig
    broadcast: BroadcastConfig
    logging: LoggingConfig


def load_config(path: str | Path) -> Config:
    """Load touch-bridge configuration from a TOML file.

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
            upstream=UpstreamConfig(**data["upstream"]),
            server=ServerConfig(**data["server"]),
            broadcast=BroadcastConfig(**data["broadcast"]),
            logging=LoggingConfig(**data["logging"]),
        )
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"invalid configuration in {config_path}: {exc}") from exc
