"""Terminal status display via title bar OSC sequences.

Uses OSC escape sequences to set the terminal window title, which does not
interfere with Claude Code's screen buffer.
"""

import os


def show_status(fd, message):
    """Show a status message in the terminal title bar."""
    os.write(fd, f"\x1b]2;parakeet-claude: {message}\x07".encode())


def clear_status(fd):
    """Restore the terminal title."""
    os.write(fd, b"\x1b]2;claude\x07")
