"""Entry point: python -m parakeet_claude

Launch claude with voice input support. Press F5 to record, F5 again to stop.
"""

import sys

from parakeet_claude.client import ParakeetClient
from parakeet_claude.pty_proxy import run_proxy


def main():
    client = ParakeetClient()

    # Pre-flight check
    if not client.ping():
        print(
            "WARNING: Parakeet server is not running.\n"
            "Voice input (F5) will not work until you start it:\n"
            "  parakeet-server\n"
            "\n"
            "Starting claude anyway...\n",
            file=sys.stderr,
        )

    # Forward all CLI args to claude
    claude_args = ["claude"] + sys.argv[1:]
    sys.exit(run_proxy(claude_args, client))


if __name__ == "__main__":
    main()
