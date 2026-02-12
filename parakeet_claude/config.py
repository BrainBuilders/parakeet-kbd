"""Configuration constants for parakeet-claude."""

import os

# Trigger key: F5 escape sequence (xterm-256color)
# Override with PARAKEET_CLAUDE_KEY env var (hex-escaped, e.g. "1b5b31357e")
_key_env = os.environ.get("PARAKEET_CLAUDE_KEY")
TRIGGER_KEY = bytes.fromhex(_key_env) if _key_env else b"\x1b[15~"

# Parakeet server socket
_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SOCKET_PATH = os.path.join(_runtime, "parakeet-claude", "parakeet.sock")

# Recording
SAMPLE_RATE = 16000
SILENCE_DURATION = "3.0"  # seconds of silence before auto-stop
SILENCE_THRESHOLD = "0.5%"

# Beeps
BEEP_START_FREQ = 880
BEEP_STOP_FREQ = 440
BEEP_DURATION = 0.1
BEEP_VOLUME = 0.3

# Timeouts
TRANSCRIBE_TIMEOUT = 30.0  # seconds
PING_TIMEOUT = 2.0
