"""PTY proxy — runs claude in a pseudo-terminal, transparently proxying all
I/O while intercepting F5 to trigger voice recording."""

import fcntl
import os
import select
import signal
import struct
import sys
import termios
import threading
import tty

from parakeet_claude.client import ParakeetClient
from parakeet_claude.key_detect import KeyDetector
from parakeet_claude.recorder import VoiceSession


def _propagate_winsize(src_fd, dst_fd):
    """Copy terminal window size from src to dst."""
    try:
        packed = fcntl.ioctl(src_fd, termios.TIOCGWINSZ, b"\x00" * 8)
        fcntl.ioctl(dst_fd, termios.TIOCSWINSZ, packed)
    except OSError:
        pass


def _copy_loop(master_fd, stdin_fd, stdout_fd, voice_session, key_detector, master_lock):
    """Main select loop: proxy bytes between real terminal and PTY master."""
    fds = [master_fd, stdin_fd]

    while True:
        try:
            rfds, _, _ = select.select(fds, [], [])
        except InterruptedError:
            # SIGWINCH interrupts select — just retry
            continue

        if master_fd in rfds:
            try:
                data = os.read(master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            os.write(stdout_fd, data)

        if stdin_fd in rfds:
            try:
                data = os.read(stdin_fd, 4096)
            except OSError:
                break
            if not data:
                # stdin closed
                if stdin_fd in fds:
                    fds.remove(stdin_fd)
                continue

            passthrough, triggered = key_detector.feed(data)

            if passthrough:
                with master_lock:
                    os.write(master_fd, passthrough)

            if triggered:
                voice_session.toggle()


def run_proxy(argv, client):
    """Fork claude in a PTY and proxy all I/O with F5 voice trigger.

    Args:
        argv: Command to run (e.g. ['claude', '--dangerously-skip-permissions'])
        client: ParakeetClient instance

    Returns:
        Child process exit code.
    """
    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()

    # Save terminal state for restore on exit
    old_attrs = termios.tcgetattr(stdin_fd)

    # Fork with PTY
    pid, master_fd = os.forkpty()

    if pid == 0:
        # Child process — exec claude
        os.execvp(argv[0], argv)
        # unreachable

    # Parent process
    try:
        # Propagate initial window size to the PTY
        _propagate_winsize(stdin_fd, master_fd)

        # Install SIGWINCH handler before setting raw mode
        def on_winch(signum, frame):
            _propagate_winsize(stdin_fd, master_fd)
            try:
                os.kill(pid, signal.SIGWINCH)
            except OSError:
                pass

        signal.signal(signal.SIGWINCH, on_winch)

        # Set real terminal to raw mode
        tty.setraw(stdin_fd)

        # Set up voice components
        master_lock = threading.Lock()
        key_detector = KeyDetector()
        voice_session = VoiceSession(master_fd, stdout_fd, master_lock, client)

        # Run the proxy loop
        _copy_loop(master_fd, stdin_fd, stdout_fd, voice_session, key_detector, master_lock)

    finally:
        # Restore terminal state
        termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, old_attrs)
        os.close(master_fd)

    # Wait for child and return its exit code
    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return 1
