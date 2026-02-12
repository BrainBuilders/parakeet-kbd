"""Unix socket client for the Parakeet ASR server."""

import socket

from parakeet_server.protocol import recv_message, send_message
from parakeet_claude.config import PING_TIMEOUT, SOCKET_PATH, TRANSCRIBE_TIMEOUT


class ParakeetClient:
    def __init__(self, socket_path=None):
        self.socket_path = socket_path or SOCKET_PATH

    def transcribe(self, audio_path, timeout=None):
        """Send an audio file to the server and return the transcribed text."""
        timeout = timeout or TRANSCRIBE_TIMEOUT
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(self.socket_path)
            send_message(sock, {"type": "transcribe", "audio_path": audio_path})
            response = recv_message(sock)
            if response["type"] == "result":
                return response["text"]
            elif response["type"] == "error":
                raise RuntimeError(response["message"])
            else:
                raise RuntimeError(f"Unexpected response: {response}")
        finally:
            sock.close()

    def ping(self, timeout=None):
        """Check if the server is alive."""
        timeout = timeout or PING_TIMEOUT
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(self.socket_path)
            send_message(sock, {"type": "ping"})
            response = recv_message(sock)
            sock.close()
            return response.get("type") == "pong"
        except (ConnectionRefusedError, FileNotFoundError, socket.timeout, OSError):
            return False
