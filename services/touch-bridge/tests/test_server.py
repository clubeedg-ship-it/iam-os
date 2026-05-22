"""Tests for the bridge WebSocket server."""

import asyncio
import json
import socket

from websockets.asyncio.client import connect

from iam_bridge.server import BridgeServer


def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


async def test_server_broadcasts_a_message_to_a_connected_client():
    port = _free_port()
    server = BridgeServer("127.0.0.1", port)
    await server.start()
    try:
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.sleep(0.05)  # let the connection register
            server.broadcast({"seq": 1, "count": 0, "touches": []})
            message = await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert json.loads(message) == {"seq": 1, "count": 0, "touches": []}
    finally:
        await server.stop()


async def test_server_broadcasts_to_every_client():
    port = _free_port()
    server = BridgeServer("127.0.0.1", port)
    await server.start()
    try:
        async with (
            connect(f"ws://127.0.0.1:{port}") as first,
            connect(f"ws://127.0.0.1:{port}") as second,
        ):
            await asyncio.sleep(0.05)
            server.broadcast({"seq": 2, "count": 0, "touches": []})
            first_message = await asyncio.wait_for(first.recv(), timeout=2.0)
            second_message = await asyncio.wait_for(second.recv(), timeout=2.0)
            assert json.loads(first_message)["seq"] == 2
            assert json.loads(second_message)["seq"] == 2
    finally:
        await server.stop()


async def test_client_count_reflects_connections():
    port = _free_port()
    server = BridgeServer("127.0.0.1", port)
    await server.start()
    try:
        assert server.client_count == 0
        async with connect(f"ws://127.0.0.1:{port}"):
            await asyncio.sleep(0.05)
            assert server.client_count == 1
    finally:
        await server.stop()


async def test_broadcast_with_no_clients_does_not_raise():
    port = _free_port()
    server = BridgeServer("127.0.0.1", port)
    await server.start()
    try:
        server.broadcast({"seq": 1, "count": 0, "touches": []})
    finally:
        await server.stop()
