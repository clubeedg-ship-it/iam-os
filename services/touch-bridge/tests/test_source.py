"""Tests for the upstream frame source."""

import asyncio
import json
import os
import tempfile

from iam_bridge.source import FrameSource


def _socket_path():
    return os.path.join(tempfile.mkdtemp(dir="/tmp"), "up.sock")


async def test_next_frame_returns_an_upstream_frame():
    path = _socket_path()
    frame = {"seq": 5, "count": 1, "touches": [{"id": 1, "x": 0.5, "y": 0.5}]}

    async def handle(_reader, writer):
        writer.write((json.dumps(frame) + "\n").encode())
        await writer.drain()

    server = await asyncio.start_unix_server(handle, path)
    source = FrameSource(path)
    try:
        assert await source.next_frame(timeout=2.0) == frame
    finally:
        await source.close()
        server.close()
        await server.wait_closed()


async def test_next_frame_returns_none_when_upstream_is_silent():
    path = _socket_path()

    async def handle(reader, _writer):
        await reader.read()  # stay connected but send nothing

    server = await asyncio.start_unix_server(handle, path)
    source = FrameSource(path)
    try:
        assert await source.next_frame(timeout=0.2) is None
    finally:
        await source.close()
        server.close()
        await server.wait_closed()


async def test_next_frame_returns_none_when_upstream_is_unavailable():
    source = FrameSource(_socket_path())  # directory exists, no socket
    try:
        assert await source.next_frame(timeout=0.2) is None
    finally:
        await source.close()
