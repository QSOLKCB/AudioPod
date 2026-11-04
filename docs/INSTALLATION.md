# Installation guide

[Home](../README.md) · [Getting started](GETTING_STARTED.md) · [Troubleshooting](TROUBLESHOOTING.md)

AudioPod runs locally from Python source. Start with a 64-bit Python 3.11–3.14 installation and [uv](https://docs.astral.sh/uv/getting-started/installation/). The desktop uses Tk. WAV export needs only the Python environment and a voice; MP3/M4B additionally need FFmpeg.

| Component | Used for | Setup |
| --- | --- | --- |
| Git | Download and update the app | System package manager, or download the repository ZIP |
| Python + Tk | App and native desktop window | Instructions below |
| uv | Install the locked Python dependencies | Official uv installer/package manager; CI uses uv 0.13.5 |
| Piper + CPU ONNX runtime | Speech generation | Installed by `uv sync --locked` |
| Cori voice, about 61 MiB | Default UK English narration | Explicit `install-voice` command or desktop button |
| FFmpeg | MP3 and chaptered M4B | Optional system package; WAV works without it |

Allow roughly 1 GB for the app environment, package cache and voice. Audio output needs additional space: Cori WAV is about 2.6 MB/minute; compressed output about 0.72 MB/minute. An M4B job retains its chapter WAVs as well.

## Ubuntu / Debian desktop

Install uv from its official instructions above, then open a terminal:

```sh
sudo apt update
sudo apt install git python3-tk ffmpeg
git clone https://github.com/QSOLKCB/AudioPod.git
cd AudioPod
uv sync --locked --python /usr/bin/python3
uv run --offline --locked python -m tkinter
```

Close the small Tk demonstration window. Selecting `/usr/bin/python3` makes uv use the interpreter matching the distribution's Tk package. The interpreter must be in the supported 3.11–3.14 range. For CLI-only use, Tk is optional; omit FFmpeg if you only want WAV.

```sh
uv run --offline --locked audiopod install-voice
uv run --offline --locked audiopod doctor
uv run --offline --locked audiopod
```

## Windows

1. Install a supported 64-bit Python from [python.org](https://www.python.org/downloads/windows/), including Tcl/Tk and the Python launcher. Python 3.14 is an option; 3.12 and 3.13 also work within the supported range.
2. Install [Git for Windows](https://git-scm.com/downloads/win) and uv using its official Windows instructions. Restart PowerShell so it sees the new commands.
3. Optional: install a Windows [FFmpeg build](https://ffmpeg.org/download.html#build-windows) and add its `bin` directory to your user PATH. Reopen PowerShell, then check `ffmpeg -version`.
4. In PowerShell, clone and select your actual Python interpreter. Change `-3.14` below if you installed a different supported version:

```powershell
git clone https://github.com/QSOLKCB/AudioPod.git
cd AudioPod
$AudioPodPython = py -3.14 -c "import sys; print(sys.executable)"
uv sync --locked --python "$AudioPodPython"
uv run --offline --locked python -m tkinter
```

Close the Tk window, then:

```powershell
uv run --offline --locked audiopod install-voice
uv run --offline --locked audiopod doctor
uv run --offline --locked audiopod
```

No PowerShell activation script is needed. If you downloaded a repository ZIP instead, extract it first and open PowerShell in the extracted folder containing `pyproject.toml`. The native Tk GUI is shared across Windows, Linux and macOS, with widget/worker smoke tests on each platform in CI. Real voice and encoding integration tests run on Linux; test a short preview on your computer before a long book.

## macOS with Homebrew

Using an existing [Homebrew](https://brew.sh/) installation:

```sh
brew install uv git python@3.12 python-tk@3.12 ffmpeg
git clone https://github.com/QSOLKCB/AudioPod.git
cd AudioPod
uv sync --locked --python "$(brew --prefix python@3.12)/bin/python3.12"
uv run --offline --locked python -m tkinter
```

The [matching Tk formula](https://formulae.brew.sh/formula/python-tk@3.12) matters. Close the demonstration window, then run the same `install-voice`, `doctor` and launch commands shown above. A supported Python.org installation with Tk is another option: select its Python executable with `uv sync --python`.

## Open the desktop after installation

| Platform | Launcher in the checkout |
| --- | --- |
| Windows | Double-click `launch-audiopod.cmd` |
| macOS | Double-click `launch-audiopod.command` in Finder |
| Linux | Run `./launch-audiopod.sh`; your file manager may also offer “Run as a program” |

These open the native desktop app using your installed environment and offline uv execution. They do not download the voice or replace the setup steps above. If a ZIP download loses executable permissions, run `chmod +x launch-audiopod.command launch-audiopod.sh` on macOS/Linux. The launchers may retain a terminal window; the app itself uses native Tk controls. You can always launch with `uv run --offline --locked audiopod gui` from the checkout.

## First setup and offline use

`uv sync --locked` downloads the locked dependencies. `audiopod install-voice` downloads and verifies the pinned model/configuration/card. These are explicit setup actions. Later, use `uv run --offline --locked audiopod`; narration does not download resources or transmit the source text. ONNX telemetry is disabled before native initialization, and native networking is checked in CI.

For a computer that will be disconnected, complete setup and a short voice preview on that computer first. Python environments contain platform-specific binaries: do not copy a Windows environment to Linux or macOS. Custom voices must be trusted eSpeak-based Piper ONNX models with the adjacent `.onnx.json`; review their individual model cards and licensing.

## Update

Stop any current render before updating. From the same checkout:

```sh
git pull --ff-only
uv sync --locked
uv run --offline --locked audiopod doctor
```

Your output folders and installed voice stay in their existing locations. Keep the previous checkout/environment if you need to resume a job after an update that changes runtime versions: resume deliberately checks the original runtime, voice and settings. This usability update retains the 0.1.0 job format.

## Remove or relocate

Delete the checkout to remove its uv-managed environment. Keep your audiobook folders wherever you want. Installed voices, preview audio and `preferences.json` live here:

| Platform | Default data folder |
| --- | --- |
| Linux | `~/.local/share/audiopod` (or `$XDG_DATA_HOME/audiopod`) |
| macOS | `~/Library/Application Support/AudioPod` |
| Windows | `%LOCALAPPDATA%/AudioPod` |

Set `AUDIOPOD_DATA_HOME` to an absolute path before launching to relocate voice/preference/preview storage. This does not move existing files or change your chosen audiobook output folder. Preferences contain paths/settings, not book text. Preview audio contains the selected source excerpt; remove previews when no longer needed.
