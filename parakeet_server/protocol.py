"""Length-prefixed JSON wire protocol over Unix domain sockets.

Request types:
    {"type": "transcribe", "audio_path": "/path/to/audio.wav"}
    {"type": "ping"}

Response types:
    {"type": "result", "text": "transcribed text"}
    {"type": "error", "message": "description"}
    {"type": "pong"}
"""

import json
import struct


def send_message(sock, obj):
    """Send a JSON message with a 4-byte big-endian length prefix."""
    data = json.dumps(obj).encode("utf-8")
    sock.sendall(struct.pack(">I", len(data)) + data)


def recv_message(sock):
    """Receive a length-prefixed JSON message. Returns the decoded object."""
    raw_len = _recv_exact(sock, 4)
    if not raw_len:
        raise ConnectionError("socket closed")
    length = struct.unpack(">I", raw_len)[0]
    data = _recv_exact(sock, length)
    return json.loads(data.decode("utf-8"))


def _recv_exact(sock, n):
    """Read exactly n bytes from the socket."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed mid-read")
        buf.extend(chunk)
    return bytes(buf)
