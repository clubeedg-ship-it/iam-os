"""Command-line entry point for the web-server.

Loads the configuration, wires the aiohttp application, and runs it until
signalled:

    python -m iam_webserver [--config PATH] [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from aiohttp import web

from iam_webserver.app import create_app
from iam_webserver.config import ConfigError, load_config
from iam_webserver.lidar_client import LidarFrameCache
from iam_webserver.logging_setup import configure_logging

_log = logging.getLogger("iam_webserver")

_DEFAULT_CONFIG = (
    Path(__file__).resolve().parent.parent / "config" / "web-server.toml"
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="iam_webserver", description="IAM-OS web server."
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_CONFIG, help="path to the TOML config"
    )
    parser.add_argument("--host", default=None, help="override the listen host")
    parser.add_argument(
        "--port", type=int, default=None, help="override the listen port"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the web-server. Returns a process exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    configure_logging(config.logging.level)

    host = args.host or config.server.host
    port = args.port or config.server.port
    _log.info("starting web-server (host=%s, port=%d)", host, port)

    cache = LidarFrameCache(
        socket_path=config.lidar.socket_path,
        reconnect_initial_s=config.lidar.reconnect_initial_s,
        reconnect_max_s=config.lidar.reconnect_max_s,
    )
    app = create_app(config, cache=cache)
    try:
        web.run_app(app, host=host, port=port, print=None)
    except KeyboardInterrupt:
        pass
    _log.info("web-server stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
