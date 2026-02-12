"""System-wide voice-to-keyboard daemon.

Loads the Parakeet ASR model, listens for a global hotkey (F9), records
audio, transcribes it in-process, and types the result into whichever
window has focus.

Supports both X11 (via pynput + xdotool) and Wayland (via evdev + ydotool).
"""

import logging
import os
import select
import subprocess
import sys
import tempfile
import threading
import warnings

MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v3"

SAMPLE_RATE = 16000
SILENCE_DURATION = "3.0"
SILENCE_THRESHOLD = "0.5%"

BEEP_START_FREQ = 880
BEEP_STOP_FREQ = 440
BEEP_DURATION = "0.1"
BEEP_VOLUME = "0.3"


def _is_wayland():
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE") == "wayland"


SESSION_IS_WAYLAND = _is_wayland()


class ParakeetKbd:
    def __init__(self, model):
        self.model = model
        self.recording = False
        self._rec_proc = None
        self._audio_path = None
        self._lock = threading.Lock()

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
            _notify("Recording... (F9 to stop)")

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


# --- Key listening ---------------------------------------------------------

def _listen_pynput(daemon):
    """Listen for F9 via pynput/Xlib (X11)."""
    from pynput import keyboard

    def on_press(key):
        if key == keyboard.Key.f9:
            daemon.toggle()

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


def _listen_evdev(daemon):
    """Listen for F9 via evdev (Wayland / kernel-level)."""
    import evdev

    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    keyboards = {
        d.fd: d for d in devices
        if evdev.ecodes.EV_KEY in d.capabilities()
    }

    if not keyboards:
        print("parakeet-kbd: ERROR — no keyboard devices found.", file=sys.stderr)
        print("  Make sure your user is in the 'input' group:", file=sys.stderr)
        print("    sudo usermod -aG input $USER", file=sys.stderr)
        print("  Then log out and back in.", file=sys.stderr)
        sys.exit(1)

    while True:
        r, _, _ = select.select(keyboards.values(), [], [])
        for dev in r:
            for event in dev.read():
                if (event.type == evdev.ecodes.EV_KEY
                        and event.value == 1
                        and event.code == evdev.ecodes.KEY_F9):
                    daemon.toggle()


# --- Text injection --------------------------------------------------------

def _type_text(text):
    """Type text into the currently focused window."""
    if SESSION_IS_WAYLAND:
        subprocess.run(
            ["ydotool", "type", "--delay", "0", "--", text],
            timeout=10,
        )
    else:
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
            timeout=10,
        )


# --- Utilities -------------------------------------------------------------

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

    session = "Wayland" if SESSION_IS_WAYLAND else "X11"
    print(f"parakeet-kbd: {session} session detected.")
    print("parakeet-kbd: listening. Press F9 to toggle voice recording.")

    daemon = ParakeetKbd(model)
    _notify("Parakeet keyboard active")

    if SESSION_IS_WAYLAND:
        _listen_evdev(daemon)
    else:
        _listen_pynput(daemon)
