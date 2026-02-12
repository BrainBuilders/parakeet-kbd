"""Detect the trigger key (F5) in the raw terminal byte stream."""

from parakeet_claude.config import TRIGGER_KEY


class KeyDetector:
    """Scans stdin byte stream for the trigger key sequence.

    Terminal emulators send escape sequences atomically in a single write,
    so they arrive as one chunk in a single read(). No state machine needed.
    """

    def feed(self, data):
        """Process raw bytes from stdin.

        Returns:
            (passthrough_bytes, triggered): passthrough is the data with any
            trigger sequence stripped out. triggered is True if the trigger
            key was found.
        """
        idx = data.find(TRIGGER_KEY)
        if idx == -1:
            return data, False

        # Strip the trigger sequence, pass everything else through
        before = data[:idx]
        after = data[idx + len(TRIGGER_KEY):]
        passthrough = before + after
        return (passthrough or None), True
