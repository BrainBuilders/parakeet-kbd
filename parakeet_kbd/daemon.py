"""System-wide voice-to-keyboard daemon.

Loads the Parakeet ASR model, listens for a global hotkey (F5), records
audio, transcribes it in-process, and types the result into whichever
window has focus via xdotool.
"""

import logging
import os
import subprocess
import sys
import tempfile
import threading
import warnings

from pynput import keyboard

MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v3"

TRIGGER_KEY = keyboard.Key.f5

SAMPLE_RATE = 16000
SILENCE_DURATION = "3.0"
SILENCE_THRESHOLD = "0.5%"

BEEP_START_FREQ = 880
BEEP_STOP_FREQ = 440
BEEP_DURATION = "0.1"
BEEP_VOLUME = "0.3"


class ParakeetKbd:
    def __init__(self, model):
        self.model = model
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
            output = self.model.transcribe([self._audio_path])
            text = output[0].text.strip() if output else ""

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
            ["notify-send", "-t", "2000", "-h",
             "string:x-canonical-private-synchronous:parakeet",
             "Parakeet", message],
            capture_output=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def main():
    print(f"Loading {MODEL_NAME}...")

    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)

    import nemo.collections.asr as nemo_asr
    model = nemo_asr.models.ASRModel.from_pretrained(model_name=MODEL_NAME)

    logging.disable(logging.NOTSET)
    warnings.resetwarnings()

    print("Model loaded.")

    daemon = ParakeetKbd(model)
    print("parakeet-kbd: listening. Press F5 to toggle voice recording.")
    _notify("Parakeet keyboard active")

    with keyboard.Listener(on_press=daemon.on_press) as listener:
        listener.join()
