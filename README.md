# parakeet-kbd

System-wide voice-to-keyboard using [Nvidia Parakeet TDT 0.6B V3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3). Press **F9** to speak, text appears wherever your cursor is — browser, editor, terminal, chat.

## How it works

A single daemon that loads the Parakeet ASR model into GPU memory, then listens for the F9 key. On press it records audio via SoX, transcribes it, and types the result into the focused window via xdotool.

## Requirements

- Linux with X11
- Python 3.10+
- NVIDIA GPU with CUDA support
- [SoX](https://sox.sourceforge.net/) (`rec` and `play` commands) for audio recording and beeps
- [xdotool](https://github.com/jordansissel/xdotool) for typing into the focused window

## Installation

```bash
git clone https://github.com/BrainBuilders/parakeet-kbd.git
cd parakeet-kbd

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
pip install -e .
```

> **Why pin torch 2.5.1?** PyTorch 2.6+ drops CUDA kernels for older GPUs (Pascal / GTX 10xx, compute capability 6.x). Pinning to 2.5.1 with the cu121 index ensures broad GPU compatibility. If you have a newer GPU (Turing/Ampere/Ada) you can skip the torch line and let `pip install -e .` pull the latest.

Install system dependencies:

```bash
# Debian/Ubuntu
sudo apt install sox libsox-fmt-all xdotool

# Fedora
sudo dnf install sox sox-plugins-freeworld xdotool

# Arch
sudo pacman -S sox xdotool
```

> **Fedora note:** `sox-plugins-freeworld` is in the [RPM Fusion free](https://rpmfusion.org/) repository. Enable it first with `sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm` if you haven't already.

## Usage

```bash
source venv/bin/activate
parakeet-kbd
```

First run downloads the model (~1.2 GB) and takes ~10s to load. Subsequent starts are faster (cached).

### Voice input flow

1. Press **F9** — a beep confirms recording started
2. Speak — recording auto-stops after 3 seconds of silence, or press **F9** again to stop manually
3. A second beep plays, a notification shows "Transcribing..."
4. Transcribed text is typed into the focused window

## License

[MIT](LICENSE)
