# parakeet-claude

Voice input for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) using [Nvidia Parakeet TDT 0.6B V3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3).

Press **F5** to speak. Your speech is transcribed and injected into Claude Code as keyboard input. All Claude Code features work unchanged — tool approvals, file editing, the full TUI.

## How it works

Two components:

- **`parakeet-server`** — Background daemon that keeps the Parakeet ASR model loaded in GPU memory. Serves transcription requests over a Unix socket. Keeps latency to ~2s instead of ~12s (avoids reloading the model every time).
- **`parakeet-claude`** — Transparent [PTY](https://en.wikipedia.org/wiki/Pseudoterminal) wrapper around `claude`. Proxies all terminal I/O byte-for-byte. Intercepts F5 to trigger voice recording, then writes the transcribed text into the PTY as if you typed it.

## Requirements

- Linux (uses PTY, Unix sockets, ALSA)
- Python 3.10+
- NVIDIA GPU with CUDA support
- [SoX](https://sox.sourceforge.net/) (`rec` and `play` commands) for audio recording and beeps
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed and on your PATH

## Installation

```bash
# Clone
git clone https://github.com/BrainBuilders/parakeet-claude.git
cd parakeet-claude

# Create venv and install
python3 -m venv venv
source venv/bin/activate
pip install torch torchvision torchaudio
pip install -e .
```

> **Note for older GPUs (Pascal / GTX 10xx):** Recent PyTorch versions dropped support for compute capability 6.x. Use `pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121` instead.

Install SoX if you don't have it:

```bash
# Debian/Ubuntu
sudo apt install sox libsox-fmt-all

# Arch
sudo pacman -S sox
```

## Usage

**Terminal 1** — Start the ASR server (keep it running):

```bash
parakeet-server
```

First run downloads the model (~1.2 GB) and takes ~10s to load. Subsequent starts are faster (cached).

**Terminal 2** — Launch Claude Code with voice input:

```bash
parakeet-claude
```

All `claude` CLI arguments pass through:

```bash
parakeet-claude --dangerously-skip-permissions
parakeet-claude --model sonnet
```

### Voice input flow

1. Press **F5** — a beep confirms recording started
2. Speak — recording auto-stops after 3 seconds of silence, or press **F5** again to stop manually
3. A second beep plays, the terminal title shows "Transcribing..."
4. Transcribed text appears at your cursor
5. Review/edit the text, then press **Enter** to submit

## Configuration

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `PARAKEET_CLAUDE_KEY` | F5 (`1b5b31357e`) | Trigger key as hex-encoded escape sequence |

## License

[MIT](LICENSE)
