"""Structured JSON logging for the lidar-service (specs.md §6, R7).

Every log record is emitted as one JSON object on stdout, which systemd's
journal captures on the appliance. Structured logs keep connection events
machine-readable and ensure nothing fails silently.
"""

from __future__ import annotations

import json
import logging
import sys
import time


class _JsonFormatter(logging.Formatter):
    """Formats each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    """Route the root logger through a JSON formatter to stdout.

    Args:
        level: log level name — ``DEBUG``, ``INFO``, ``WARNING``, or ``ERROR``.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())
