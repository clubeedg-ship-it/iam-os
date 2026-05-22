"""Typed configuration for the lidar-service.

Loads ``config/lidar-service.toml`` into frozen, typed dataclasses. Any value
may be overridden at runtime by an environment variable named
``IAM_LIDAR_<SECTION>_<KEY>`` (uppercase): the TOML file provides the
defaults, environment variables override them.

This module deliberately does not use ``from __future__ import annotations``
so that ``dataclasses.fields()`` reports real types, which the environment
override coercion relies on.
"""

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, get_args, get_origin


class ConfigError(Exception):
    """Raised when configuration is missing, unreadable, or incomplete."""


@dataclass(frozen=True, slots=True)
class DeviceConfig:
    """The LiDAR device and how to connect to it."""

    driver: str
    port: str
    baud_rates: list[int]
    adapter_keywords: list[str]
    connect_timeout_s: float


@dataclass(frozen=True, slots=True)
class ConnectionConfig:
    """Reconnect-backoff and watchdog tuning."""

    backoff_initial_s: float
    backoff_max_s: float
    backoff_factor: float
    watchdog_timeout_s: float


@dataclass(frozen=True, slots=True)
class DetectionConfig:
    """Touch-detection thresholds, all in millimetres or point counts."""

    distance_min_mm: float
    distance_max_mm: float
    baseline_threshold_mm: float
    baseline_min_points: int
    cluster_tolerance_mm: float
    cluster_min_points: int
    cluster_max_points: int
    track_tolerance_mm: float


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """Where touch frames are published."""

    socket_path: str


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Logging behaviour."""

    level: str


@dataclass(frozen=True, slots=True)
class Config:
    """The complete lidar-service configuration."""

    device: DeviceConfig
    connection: ConnectionConfig
    detection: DetectionConfig
    output: OutputConfig
    logging: LoggingConfig


_SECTIONS: dict[str, type] = {
    "device": DeviceConfig,
    "connection": ConnectionConfig,
    "detection": DetectionConfig,
    "output": OutputConfig,
    "logging": LoggingConfig,
}


def _coerce(raw: str, annotation: Any) -> Any:
    """Convert an environment-variable string to a field's declared type."""
    if get_origin(annotation) is list:
        (item_type,) = get_args(annotation)
        return [
            _coerce(piece.strip(), item_type)
            for piece in raw.split(",")
            if piece.strip()
        ]
    if annotation is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if annotation is int:
        return int(raw)
    if annotation is float:
        return float(raw)
    return raw


def _build_section(
    name: str,
    section_type: type,
    table: Mapping[str, Any],
    env: Mapping[str, str],
) -> Any:
    """Build one section dataclass from its TOML table plus env overrides."""
    values: dict[str, Any] = {}
    for field in fields(section_type):
        env_key = f"IAM_LIDAR_{name}_{field.name}".upper()
        if env_key in env:
            values[field.name] = _coerce(env[env_key], field.type)
        elif field.name in table:
            values[field.name] = table[field.name]
        else:
            raise ConfigError(f"missing config value [{name}].{field.name}")
    return section_type(**values)


def load_config(path: str | Path, *, env: Mapping[str, str] | None = None) -> Config:
    """Load configuration from a TOML file, applying environment overrides.

    Args:
        path: path to a lidar-service TOML config file.
        env: environment mapping to read overrides from; defaults to
            ``os.environ``.

    Returns:
        A fully populated :class:`Config`.

    Raises:
        ConfigError: if the file is missing, is not valid TOML, or omits a
            required value.
    """
    env = os.environ if env is None else env
    config_path = Path(path)
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {config_path}: {exc}") from exc

    sections = {
        name: _build_section(name, section_type, data.get(name, {}), env)
        for name, section_type in _SECTIONS.items()
    }
    return Config(**sections)
