"""Command-line entry point for the touch-bridge.

Reads touch frames from lidar-service and re-broadcasts them on the WebSocket
touch contract, falling back to heartbeat frames when upstream is silent:

    python -m iam_bridge [--config PATH] [--socket PATH] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from pathlib import Path

from iam_bridge.config import ConfigError, load_config
from iam_bridge.contract import empty_message, to_contract_message
from iam_bridge.health import BridgeHealth
from iam_bridge.logging_setup import configure_logging
from iam_bridge.server import BridgeServer
from iam_bridge.source import FrameSource

_log = logging.getLogger("iam_bridge")

_DEFAULT_CONFIG = (
    Path(__file__).resolve().parent.parent / "config" / "touch-bridge.toml"
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="iam_bridge", description="IAM-OS touch bridge."
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_CONFIG, help="path to the TOML config"
    )
    parser.add_argument(
        "--socket", default=None, help="override the upstream lidar-service socket"
    )
    parser.add_argument(
        "--port", type=int, default=None, help="override the WebSocket server port"
    )
    return parser.parse_args(argv)


async def _run(
    *, socket_path: str, host: str, port: int, heartbeat_interval_s: float
) -> None:
    """Pump upstream frames onto the WebSocket until signalled to stop."""
    server = BridgeServer(host, port)
    source = FrameSource(socket_path)
    health = BridgeHealth()
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    await server.start()
    seq = 0
    try:
        while not stop.is_set():
            frame = await source.next_frame(timeout=heartbeat_interval_s)
            seq += 1
            if frame is None:
                health.record_silence()
                server.broadcast(empty_message(seq))
            else:
                health.record_frame()
                server.broadcast(to_contract_message(frame, seq))
    finally:
        await source.close()
        await server.stop()


def main(argv: list[str] | None = None) -> int:
    """Run the touch-bridge. Returns a process exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    configure_logging(config.logging.level)

    socket_path = args.socket or config.upstream.socket_path
    port = args.port or config.server.port
    _log.info("starting touch-bridge (upstream=%s, port=%d)", socket_path, port)

    try:
        asyncio.run(
            _run(
                socket_path=socket_path,
                host=config.server.host,
                port=port,
                heartbeat_interval_s=config.broadcast.heartbeat_interval_s,
            )
        )
    except KeyboardInterrupt:
        pass
    _log.info("touch-bridge stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
