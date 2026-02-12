"""Parakeet ASR server — keeps the model loaded in GPU memory and serves
transcription requests over a Unix domain socket."""

import logging
import os
import signal
import socket
import sys
import warnings

from parakeet_server.protocol import recv_message, send_message

MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v3"


def _get_socket_dir():
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(runtime, "parakeet-claude")


def _get_socket_path():
    return os.path.join(_get_socket_dir(), "parakeet.sock")


def _get_pid_path():
    return os.path.join(_get_socket_dir(), "parakeet.pid")


def _load_model():
    """Load the ASR model, suppressing NeMo/PyTorch log noise."""
    # Suppress noisy startup logs
    warnings.filterwarnings("ignore")
    logging.disable(logging.WARNING)

    import nemo.collections.asr as nemo_asr

    model = nemo_asr.models.ASRModel.from_pretrained(model_name=MODEL_NAME)

    # Re-enable logging
    logging.disable(logging.NOTSET)
    warnings.resetwarnings()

    return model


def _handle_connection(conn, model):
    """Handle a single client connection."""
    try:
        request = recv_message(conn)
    except ConnectionError:
        return

    req_type = request.get("type")

    if req_type == "ping":
        send_message(conn, {"type": "pong", "model": MODEL_NAME})
        return

    if req_type == "transcribe":
        audio_path = request.get("audio_path", "")
        if not os.path.isfile(audio_path):
            send_message(conn, {"type": "error", "message": f"File not found: {audio_path}"})
            return
        try:
            output = model.transcribe([audio_path])
            text = output[0].text if output else ""
            send_message(conn, {"type": "result", "text": text})
        except Exception as e:
            send_message(conn, {"type": "error", "message": str(e)})
        return

    send_message(conn, {"type": "error", "message": f"Unknown request type: {req_type}"})


def run_server():
    sock_dir = _get_socket_dir()
    sock_path = _get_socket_path()
    pid_path = _get_pid_path()

    # Create socket directory
    os.makedirs(sock_dir, exist_ok=True)

    # Check for existing server
    if os.path.exists(pid_path):
        try:
            with open(pid_path) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)  # check if alive
            print(f"Server already running (pid {old_pid}). Exiting.", file=sys.stderr)
            sys.exit(1)
        except (OSError, ValueError):
            pass  # stale pid file

    # Write PID file
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))

    # Clean up stale socket
    if os.path.exists(sock_path):
        os.unlink(sock_path)

    # Load model
    print(f"Loading {MODEL_NAME}...")
    model = _load_model()
    print("Model loaded. Ready.")

    # Create socket
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(5)

    # Cleanup handler
    def cleanup(signum=None, frame=None):
        print("\nShutting down...")
        srv.close()
        try:
            os.unlink(sock_path)
        except OSError:
            pass
        try:
            os.unlink(pid_path)
        except OSError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    print(f"Listening on {sock_path}")

    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            break
        try:
            _handle_connection(conn, model)
        except Exception as e:
            print(f"Error handling connection: {e}", file=sys.stderr)
        finally:
            conn.close()
