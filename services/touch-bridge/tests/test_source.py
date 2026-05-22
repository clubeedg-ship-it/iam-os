"""Tests for the upstream frame source."""

import asyncio
import json
import os
import tempfile

from iam_bridge.source import _BACKOFF_INITIAL_S, _BACKOFF_MAX_S, FrameSource


def _socket_path():
    return os.path.join(tempfile.mkdtemp(dir="/tmp"), "up.sock")


class _FakeClock:
    """A monotonic clock the test advances by hand — no real waiting."""

    def __init__(self) -> None:
        self._now = 1000.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


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


async def test_failed_connects_are_spaced_by_growing_backoff():
    """While upstream is down, connect attempts back off exponentially."""
    clock = _FakeClock()
    attempts = 0
    real_connect = FrameSource._connect

    async def counting_connect(self):
        nonlocal attempts
        attempts += 1
        return await real_connect(self)

    source = FrameSource(_socket_path(), monotonic=clock)  # no socket: connect fails
    object.__setattr__(source, "_connect", counting_connect.__get__(source))
    try:
        # First call attempts immediately.
        assert await source.next_frame(timeout=0.0) is None
        assert attempts == 1

        # Before the initial backoff elapses, no further attempt is made.
        clock.advance(_BACKOFF_INITIAL_S / 2)
        assert await source.next_frame(timeout=0.0) is None
        assert attempts == 1

        # Once the initial delay has elapsed, a second attempt happens.
        clock.advance(_BACKOFF_INITIAL_S)
        assert await source.next_frame(timeout=0.0) is None
        assert attempts == 2

        # The window has now doubled: half of it is still too soon.
        clock.advance(_BACKOFF_INITIAL_S)
        assert await source.next_frame(timeout=0.0) is None
        assert attempts == 2

        # The full (doubled) window allows the third attempt.
        clock.advance(_BACKOFF_INITIAL_S * 2)
        assert await source.next_frame(timeout=0.0) is None
        assert attempts == 3
    finally:
        await source.close()


async def test_backoff_is_capped_at_the_maximum():
    """The backoff window never grows past the configured maximum."""
    clock = _FakeClock()
    source = FrameSource(_socket_path(), monotonic=clock)
    try:
        # Drive the backoff well past the cap. Each iteration: wait out the
        # current window, then make one (failing) attempt.
        for _ in range(20):
            clock.advance(_BACKOFF_MAX_S)
            assert await source.next_frame(timeout=0.0) is None
        # One more attempt: the cap holds, so _BACKOFF_MAX_S is always enough.
        clock.advance(_BACKOFF_MAX_S)
        before = source._next_attempt_at
        assert await source.next_frame(timeout=0.0) is None
        assert source._next_attempt_at - before <= _BACKOFF_MAX_S + 1e-6
    finally:
        await source.close()


async def test_successful_connection_resets_the_backoff():
    """A successful connect clears the backoff so the next drop starts fresh."""
    clock = _FakeClock()
    path = _socket_path()
    frame = {"seq": 1, "count": 0, "touches": []}

    async def handle(_reader, writer):
        # Send one frame, then close — the EOF makes the source disconnect.
        writer.write((json.dumps(frame) + "\n").encode())
        await writer.drain()
        writer.close()

    source = FrameSource(path, monotonic=clock)  # no socket yet: connect fails
    try:
        # Upstream is down: grow the backoff with two failed attempts.
        assert await source.next_frame(timeout=0.0) is None
        clock.advance(_BACKOFF_INITIAL_S)
        assert await source.next_frame(timeout=0.0) is None
        # Backoff has now grown past its initial value and a wait is pending.
        assert source._backoff_s > _BACKOFF_INITIAL_S
        assert source._next_attempt_at > clock()

        # Upstream comes up; a connect succeeds and must reset the backoff.
        server = await asyncio.start_unix_server(handle, path)
        try:
            clock.advance(_BACKOFF_MAX_S)  # wait out the grown window
            assert await source.next_frame(timeout=2.0) == frame
            # The successful connect reset the backoff to its initial state.
            assert source._backoff_s == _BACKOFF_INITIAL_S
            assert source._next_attempt_at == 0.0
        finally:
            server.close()
            await server.wait_closed()

        # The server's EOF makes the next read disconnect.
        assert await source.next_frame(timeout=2.0) is None  # reads EOF
        # The socket is gone again, so the next attempt fails. Because the
        # earlier success reset the backoff, that failure schedules the
        # following attempt only _BACKOFF_INITIAL_S out — not the grown value.
        attempt_at = clock()
        assert await source.next_frame(timeout=0.0) is None  # failed reconnect
        assert source._next_attempt_at - attempt_at == _BACKOFF_INITIAL_S
    finally:
        await source.close()
