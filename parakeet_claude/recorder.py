"""Voice recording session — beep, record, transcribe, inject."""

import os
import subprocess
import tempfile
import threading
import time

from parakeet_claude.client import ParakeetClient
from parakeet_claude.config import (
    BEEP_DURATION,
    BEEP_START_FREQ,
    BEEP_STOP_FREQ,
    BEEP_VOLUME,
    SAMPLE_RATE,
    SILENCE_DURATION,
    SILENCE_THRESHOLD,
)
from parakeet_claude.status import clear_status, show_status


def _play_beep(frequency, duration=BEEP_DURATION):
    """Play a short synthetic tone via sox's play command."""
    try:
        subprocess.run(
            [
                "play", "-q", "-n",
                "synth", str(duration), "sine", str(frequency),
                "vol", str(BEEP_VOLUME),
            ],
            timeout=2,
            capture_output=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


class VoiceSession:
    """Manages a single voice recording -> transcription -> injection cycle.

    Runs in a background thread so the PTY copy loop is not blocked.
    """

    def __init__(self, master_fd, stdout_fd, master_fd_lock, client):
        self.master_fd = master_fd
        self.stdout_fd = stdout_fd
        self.master_fd_lock = master_fd_lock
        self.client = client
        self.recording = False
        self._rec_proc = None
        self._audio_path = None
        self._thread = None

    def toggle(self):
        """Called on each F5 press. Starts or stops recording."""
        if not self.recording:
            self._start()
        else:
            self._stop()

    def _start(self):
        self.recording = True
        fd, self._audio_path = tempfile.mkstemp(suffix=".wav", prefix="parakeet_claude_")
        os.close(fd)
        self._thread = threading.Thread(target=self._record_flow, daemon=True)
        self._thread.start()

    def _stop(self):
        """Manual stop via second F5 press."""
        if self._rec_proc and self._rec_proc.poll() is None:
            self._rec_proc.terminate()
            try:
                self._rec_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._rec_proc.kill()

    def _record_flow(self):
        try:
            # Start beep
            _play_beep(BEEP_START_FREQ)
            show_status(self.stdout_fd, "Recording... (F5 to stop)")

            # Record with silence auto-stop
            self._rec_proc = subprocess.Popen([
                "rec", "-q",
                "-r", str(SAMPLE_RATE), "-c", "1", "-b", "16",
                self._audio_path,
                "silence", "1", "0.1", SILENCE_THRESHOLD,
                "1", SILENCE_DURATION, SILENCE_THRESHOLD,
            ])
            self._rec_proc.wait()

            # Stop beep
            _play_beep(BEEP_STOP_FREQ)

            # Check if recording produced anything useful
            if not os.path.isfile(self._audio_path):
                show_status(self.stdout_fd, "Recording failed")
                time.sleep(2)
                clear_status(self.stdout_fd)
                return

            file_size = os.path.getsize(self._audio_path)
            if file_size < 1000:  # too small, probably no speech
                show_status(self.stdout_fd, "No speech detected")
                time.sleep(1)
                clear_status(self.stdout_fd)
                return

            # Transcribe
            show_status(self.stdout_fd, "Transcribing...")

            try:
                text = self.client.transcribe(self._audio_path)
            except (ConnectionRefusedError, FileNotFoundError, OSError):
                show_status(self.stdout_fd, "Server not running! Start: parakeet-server")
                time.sleep(3)
                clear_status(self.stdout_fd)
                return
            except Exception as e:
                show_status(self.stdout_fd, f"Transcription error: {e}")
                time.sleep(2)
                clear_status(self.stdout_fd)
                return

            text = text.strip() if text else ""
            if not text:
                show_status(self.stdout_fd, "No speech detected")
                time.sleep(1)
                clear_status(self.stdout_fd)
                return

            # Inject text into Claude Code's PTY input
            with self.master_fd_lock:
                os.write(self.master_fd, text.encode("utf-8"))

            clear_status(self.stdout_fd)

        finally:
            self.recording = False
            if self._audio_path and os.path.exists(self._audio_path):
                try:
                    os.unlink(self._audio_path)
                except OSError:
                    pass
