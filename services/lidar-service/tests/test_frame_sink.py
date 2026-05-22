"""Tests for the touch-frame sink."""

import json
import os
import socket
import tempfile
import threading
import time

from iam_lidar.frames import Touch, TouchFrame
from iam_lidar.output.frame_sink import FrameSink, frame_to_dict


def _touch(touch_id=1):
    return Touch(id=touch_id, x=0.5, y=0.5, raw_x_mm=0.0, raw_y_mm=0.0, size=9)


def test_frame_to_dict_of_an_empty_frame():
    assert frame_to_dict(TouchFrame(seq=7)) == {"seq": 7, "count": 0, "touches": []}


def test_frame_to_dict_emits_only_contract_fields():
    touch = Touch(id=3, x=0.25, y=0.75, raw_x_mm=120.0, raw_y_mm=340.0, size=11)
    assert frame_to_dict(TouchFrame(seq=9, touches=(touch,))) == {
        "seq": 9,
        "count": 1,
        "touches": [{"id": 3, "x": 0.25, "y": 0.75}],
    }


def test_sink_publishes_frames_to_a_connected_client():
    socket_path = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s")
    sink = FrameSink(socket_path)
    sink.start()
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(socket_path)
        time.sleep(0.1)  # let the accept thread register the client
        sink.publish(TouchFrame(seq=1, touches=(_touch(),)))
        client.settimeout(2.0)
        message = json.loads(client.makefile().readline())
        assert message["seq"] == 1
        assert message["count"] == 1
        assert message["touches"][0]["id"] == 1
    finally:
        client.close()
        sink.close()


def test_publish_with_no_client_is_silently_dropped():
    socket_path = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s")
    sink = FrameSink(socket_path)
    sink.start()
    try:
        sink.publish(TouchFrame(seq=1))  # must not raise
    finally:
        sink.close()


def _accept_thread(sink):
    """Return the daemon accept-loop thread started by ``sink``."""
    for thread in threading.enumerate():
        if thread.name.startswith("Thread-") and thread.daemon and thread.is_alive():
            target = getattr(thread, "_target", None)
            if target is not None and target.__name__ == "_accept_loop":
                return thread
    return None


def test_close_while_accept_loop_runs_shuts_down_cleanly():
    """close() racing the running accept loop terminates it without error.

    The accept loop reads self._server (None check, then accept()) while
    close() concurrently nulls it. The fix captures the reference into a
    local so the loop cannot hit an AttributeError mid-iteration. The window
    is tiny and nondeterministic, so this is a behavioral safety net rather
    than a deterministic reproduction of the failure.
    """
    socket_path = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s")
    sink = FrameSink(socket_path)
    sink.start()

    accept_thread = _accept_thread(sink)
    assert accept_thread is not None and accept_thread.is_alive()

    # A client is mid-handshake while close() races the accept loop.
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(socket_path)
        sink.close()  # must not raise; nulls self._server out of band
    finally:
        client.close()

    accept_thread.join(timeout=2.0)
    assert not accept_thread.is_alive(), "accept loop did not terminate"
    assert sink._server is None


def test_repeated_start_close_cycles_are_clean():
    """Starting and closing the sink several times leaves no dangling state."""
    socket_path = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s")
    for _ in range(5):
        sink = FrameSink(socket_path)
        sink.start()
        sink.close()  # must not raise
        assert sink._server is None
        assert not os.path.exists(socket_path)
