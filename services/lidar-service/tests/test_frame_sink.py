"""Tests for the touch-frame sink."""

import json
import os
import socket
import tempfile
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
