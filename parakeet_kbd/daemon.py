"""System-wide voice-to-keyboard daemon.

Listens for a global hotkey (F5), records audio, transcribes via
parakeet-server, and types the result into whichever window has focus.
"""

import os
import socket
import subprocess
import tempfile
import threading

from pynput import keyboard

from parakeet_server.protocol import recv_message, send_message

# --- Config ---------------------------------------------------------------

_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SOCKET_PATH = os.path.join(_runtime, "parakeet-claude", "parakeet.sock")

TRIGGER_KEY = keyboard.Key.f5

SAMPLE_RATE = 16000
SILENCE_DURATION = "3.0"
SILENCE_THRESHOLD = "0.5%"

BEEP_START_FREQ = 880
BEEP_STOP_FREQ = 440
BEEP_DURATION = "0.1"
BEEP_VOLUME = "0.3"

TRANSCRIBE_TIMEOUT = 30.0


# --- Daemon ----------------------------------------------------------------

class ParakeetKbd:
    def __init__(self):
        self.recording = False
        self._rec_proc = None
        self._audio_path = None
        self._lock = threading.Lock()

    def on_press(self, key):
        if key == TRIGGER_KEY:
            self.toggle()

    def toggle(self):
        with self._lock:
            if not self.recording:
                self._start_recording()
            else:
                self._stop_recording()

    def _start_recording(self):
        self.recording = True
        fd, self._audio_path = tempfile.mkstemp(
            suffix=".wav", prefix="parakeet_kbd_"
        )
        os.close(fd)
        threading.Thread(target=self._record_flow, daemon=True).start()

    def _stop_recording(self):
        if self._rec_proc and self._rec_proc.poll() is None:
            self._rec_proc.terminate()
            try:
                self._rec_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._rec_proc.kill()

    def _record_flow(self):
        try:
            _play_beep(BEEP_START_FREQ)
            _notify("Recording... (F5 to stop)")

            self._rec_proc = subprocess.Popen([
                "rec", "-q",
                "-r", str(SAMPLE_RATE), "-c", "1", "-b", "16",
                self._audio_path,
                "silence", "1", "0.1", SILENCE_THRESHOLD,
                "1", SILENCE_DURATION, SILENCE_THRESHOLD,
            ])
            self._rec_proc.wait()

            _play_beep(BEEP_STOP_FREQ)

            if not os.path.isfile(self._audio_path):
                _notify("Recording failed")
                return

            if os.path.getsize(self._audio_path) < 1000:
                _notify("No speech detected")
                return

            _notify("Transcribing...")
            text = _transcribe(self._audio_path)

            if text:
                _type_text(text)
            else:
                _notify("No speech detected")

        except Exception as exc:
            _notify(f"Error: {exc}")

        finally:
            self.recording = False
            if self._audio_path and os.path.exists(self._audio_path):
                try:
                    os.unlink(self._audio_path)
                except OSError:
                    pass


# --- Helpers ---------------------------------------------------------------

def _transcribe(audio_path):
    """Send audio to parakeet-server and return transcribed text."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(TRANSCRIBE_TIMEOUT)
    try:
        sock.connect(SOCKET_PATH)
        send_message(sock, {"type": "transcribe", "audio_path": audio_path})
        response = recv_message(sock)
        if response["type"] == "result":
            return response.get("text", "").strip()
        if response["type"] == "error":
            raise RuntimeError(response["message"])
        return ""
    finally:
        sock.close()


def _type_text(text):
    """Type text into the currently focused window via xdotool."""
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        timeout=10,
    )


def _play_beep(frequency):
    """Play a short beep via SoX."""
    try:
        subprocess.run(
            [
                "play", "-q", "-n",
                "synth", BEEP_DURATION, "sine", str(frequency),
                "vol", BEEP_VOLUME,
            ],
            timeout=2,
            capture_output=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def _notify(message):
    """Show a desktop notification."""
    try:
        subprocess.run(
            ["notify-send", "-t", "2000", "-h", "string:x-canonical-private-synchronous:parakeet", "Parakeet", message],
            capture_output=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def main():
    print("parakeet-kbd: checking server...")
    # Quick ping
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(SOCKET_PATH)
        send_message(sock, {"type": "ping"})
        resp = recv_message(sock)
        sock.close()
        if resp.get("type") == "pong":
            print(f"parakeet-kbd: server OK ({resp.get('model', '?')})")
        else:
            print("parakeet-kbd: WARNING — unexpected server response")
    except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
        print(f"parakeet-kbd: WARNING — server not reachable ({exc})")
        print("  Start it first: parakeet-server")

    daemon = ParakeetKbd()
    print("parakeet-kbd: listening. Press F5 to toggle voice recording.")
    _notify("Parakeet keyboard active")

    with keyboard.Listener(on_press=daemon.on_press) as listener:
        listener.join()
