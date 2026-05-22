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


@dataclass(frozen=True, slots=True)
class UpstreamConfig:
    """The lidar-service socket the bridge reads frames from."""

    socket_path: str


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """The WebSocket address the bridge serves on."""

    host: str
    port: int


@dataclass(frozen=True, slots=True)
class BroadcastConfig:
    """How often an empty frame is sent when upstream is silent."""

    heartbeat_interval_s: float


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Logging behaviour."""

    level: str


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
