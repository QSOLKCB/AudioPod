# AudioPod

**[Installation guide](docs/INSTALLATION.md) · [Getting started](docs/GETTING_STARTED.md) · [Troubleshooting and recovery](docs/TROUBLESHOOTING.md)**

[Natural narration: delivery controls, QEC-informed validation and comparison evidence](docs/NATURAL_NARRATION.md)

**Turn a book into a listen.** Convert local EPUB books, text and Markdown into spoken audio with a local Piper voice. The native desktop GUI runs on Windows, Linux and macOS; it shares the importer and rendering engine with the CLI.

No account, hosted inference, telemetry, subscription, Docker or Node.js. Install the Python dependencies and a voice once; narration then works offline. The app never sends your book to a service.

AudioPod sets `ORT_DISABLE_TELEMETRY=1` before importing ONNX Runtime, and also disables telemetry through its API. The startup environment opt-out matters: the API alone does not suppress all native runtime telemetry.

## Features

- Import DRM-free EPUB in reading order, UTF-8 TXT, Markdown, or pasted text. Preview the words and select sections before narrating.
- Install **Cori, UK English**, or choose a local eSpeak-based Piper `.onnx` voice with its adjacent `.onnx.json`. Multi-speaker voices have a numeric speaker ID control.
- **Natural delivery** plans sentence/paragraph phrasing, credits existing quiet time, fades joins and uses one chapter-wide gain to preserve relative phrase levels. Adjustable pauses and an **Original** mode support listening comparisons and older saved jobs. The voice's trained noise/timing defaults are retained.
- Export chapter WAVs, chapter MP3s, or a single M4B audiobook with chapter markers. M4B exports also retain chapter WAVs for the listening page.
- Open `listen.html`: chapter navigation, ±15-second seeking, playback speed, keyboard controls, chapter text and browser-local position bookmarks. No server or connection required.
- Cancel at an audio chunk boundary and resume completed chapters after checking their hashes. The model loads once per job; bounded chunks and a four-thread CPU default keep long books manageable.
- Check setup locally with `audiopod doctor`; restore a job's settings with `audiopod resume` or **Resume folder…**. The desktop remembers your voice/settings, suggests a fresh book-specific folder, offers larger reading text and shows an approximate listening length.
- The player includes a sleep timer and restart control. Resume checks all saved audio before writing, and short-chapter jobs batch player updates while saving every chapter receipt.

## First run

Requires Python **3.11–3.14** and [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 is recommended. The desktop needs Tk. MP3 and M4B need [FFmpeg](https://ffmpeg.org/download.html) on `PATH`; WAV does not.

```sh
git clone https://github.com/QSOLKCB/AudioPod.git
cd AudioPod
uv sync --locked
uv run --offline --locked audiopod
```

1. Choose **Install Cori voice…** and confirm the approximately 61 MiB download. This is the only app operation that contacts the internet. Files are verified against pinned SHA-256 hashes.
2. **Open book…** or **Paste text…**, inspect the preview and select sections. Front matter and part headings are selectable too.
3. Choose a new output folder, delivery, pause length, voice speed and format. **Voice preview** renders up to 400 characters from the first selected section into a separate local preview folder.
4. Choose **Create audiobook**, then **Listen**. Keep the output folder together, or copy `book.m4b` alone to an audiobook player.

After setup, use `launch-audiopod.cmd` on Windows, `launch-audiopod.command` on macOS, or `./launch-audiopod.sh` on Linux. See the [platform installation guide](docs/INSTALLATION.md#open-the-desktop-after-installation) for launch instructions.

### Ubuntu / Debian

Use your distribution Python so Tk and Python match:

```sh
sudo apt install python3-tk ffmpeg
uv sync --locked --python /usr/bin/python3
uv run --offline --locked audiopod
```

If an existing uv environment uses a Python without Tk, select the intended interpreter with `uv sync --python /usr/bin/python3 --locked` and allow uv to recreate it. No manual environment activation is needed.

### Windows and macOS

Use a Python installation with Tk enabled, selecting its interpreter with `uv sync --locked --python /path/to/python`. Confirm Tk with `uv run --offline python -m tkinter`. Official Python installers normally include Tk. Homebrew users can install matching `python@3.12` and `python-tk@3.12`, plus `uv` and optionally `ffmpeg`, and select the Homebrew Python interpreter when syncing.

This version is a source/CLI/desktop app, not a signed native installer or self-contained EXE.

## CLI

The importer and help work without Piper: `python -m audiopod inspect book.epub`. Use the uv environment for narration.

```sh
# Explicit one-time voice download; no book is involved.
uv run --offline --locked audiopod install-voice

# Check setup without any downloads.
uv run --offline --locked audiopod doctor

# See section numbers before choosing what to narrate.
uv run --offline --locked audiopod inspect book.epub

# Full audiobook with chapter markers.
uv run --offline --locked audiopod render book.epub --output output/my-book --format m4b

# Selected sections and slower delivery.
uv run --offline --locked audiopod render book.epub --output output/selection \
  --chapters 2,4-7 --speed 0.9 --format mp3

# Repeat the SAME command/settings, adding --resume after cancellation.
uv run --offline --locked audiopod render book.epub --output output/my-book --format m4b --resume

# Or restore the original selection/settings automatically.
uv run --offline --locked audiopod resume book.epub --output output/my-book

# Small original sample supplied with the app.
uv run --offline --locked audiopod render examples/first-listen.md --output output/first-listen
```

`--model /path/to/voice.onnx` selects another voice. `--title` and `--author` override metadata. `--speaker` selects a speaker ID (default 0). `--threads 1` through `--threads 32` set the CPU budget (default 4, capped to available CPUs). Voice speed accepts 0.5–2.0. Playback speed in the listening page changes without re-rendering. Ctrl+C, the Cancel button, or Escape in the desktop requests cancellation; a chunk already being synthesized finishes before stopping.

New jobs use `--style natural`; `--pause-scale 0.5` through `2.0` adjusts supplemental pauses. `--style original` retains the earlier renderer. Use `audiopod resume` to restore an older job automatically, or include `--style original` with a manual `render ... --resume`. Delivery and pause settings cannot be mixed within a saved job. [Details and a public A/B listening sample](docs/NATURAL_NARRATION.md).

## Output and recovery

| File | Purpose |
| --- | --- |
| `0001.wav` or `0001.mp3` | Completed section, numbered by original reading order |
| `book.m4b` | AAC audiobook with chapter markers, in M4B mode |
| `listen.html` | Portable offline player, including selected chapter text |
| `playlist.m3u` | Playlist for compatible audio players |
| `audiopod.json` | Source/model/config/settings fingerprints and completed-audio hashes |

Natural jobs also record measured pre-encoding PCM levels and frame counts. These are signal checks, not a score for pronunciation or naturalness; compressed audio can have different peaks.

The app refuses to overwrite a populated folder. Resume requires the same text, metadata, selection, voice and settings, and refuses missing or modified audio. An unfinished chapter restarts from its beginning. Completed chapters remain usable after cancellation.

A `.audiopod-lock` directory prevents simultaneous writes. Normal cancellation removes it. After a forced kill or power loss, **verify no AudioPod job is using that folder**, remove the empty lock directory, then resume. A crash between audio rename and receipt writing can leave an untracked audio file; move that specific file aside before resuming. Temporary `.chapter-*`, `.encode-*` and `.write-*` leftovers can be removed when no job is running. Existing audio is never silently regenerated over a changed file.

Voices and previews are stored under `~/.local/share/audiopod` on Linux, `~/Library/Application Support/AudioPod` on macOS, or `%LOCALAPPDATA%/AudioPod` on Windows. `AUDIOPOD_DATA_HOME` overrides this location. Delete unwanted preview folders when no longer needed. Voice weights and books are not part of the repository.

## Import and accessibility limits

- Narration does not translate, summarize or rewrite text. Whitespace is normalized. Markdown front matter, heading markers, common emphasis markers and link destinations are removed while visible text is retained. Complex Markdown extensions are not a full CommonMark implementation: inspect the preview.
- EPUB navigation, scripts/styles, hidden elements and non-linear spine items are omitted. Paragraphs, headings and Unicode punctuation are retained. Image alt text can be read; images are not interpreted. PDF/OCR, DOCX, web fetching and DRM removal are not supported. EPUBs with encrypted resources, including encrypted fonts, need a plain export first.
- Synthetic pronunciation, especially invented names, needs human review. Timing and pronunciation are not guaranteed identical across voice/runtime versions. Text display is chapter-level, without word-synchronized highlighting.
- The desktop uses native Tk widgets and keyboard focus. Screen-reader behaviour still needs target-desktop testing; it is not certified. The HTML player has native controls, semantic headings, visible focus and labelled buttons. Bookmarks depend on browser support for local storage on `file:` pages and do not transfer to another browser.
- First setup downloads Python packages and a voice. Narration supports eSpeak-based voices only; other Piper phonemizers can require extra downloads. Automatic Arabic diacritization is disabled. Match your voice language to the source text.
- Text imports are limited to 20 MiB; EPUB archives to 256 MiB, expanded archives to 512 MiB and individual text entries to 16 MiB. WAV chapters stop before the RIFF size limit. Cori WAV storage is about 2.6 MB/minute; 96 kbps MP3/M4B is about 0.72 MB/minute. M4B creation also needs space for intermediate WAVs.
- Natural uses a temporary float32 spool per unfinished chapter, about twice its PCM WAV size, alongside the WAV while finalizing. Use shorter chapters if temporary disk space is limited.

## Development

```sh
uv run --offline --locked python -m unittest discover -s tests -v
uv run --offline --locked python scripts/smoke_voice.py  # voice installed first
uv run --offline --locked python scripts/compare_narration.py --output output/narration-comparison
xvfb-run -a uv run --offline --locked python scripts/smoke_gui.py  # Linux
uv run --locked --with quickjs==1.19.4 python scripts/smoke_player.py  # test-only JS engine
uv run --offline --locked python scripts/benchmark_splitter.py
uv build --no-sources
```

Core tests use generated fixtures, including tone WAVs for encoder checks. The separate speech test uses actual Piper inference and blocks Python socket connections during narration; Linux CI also traces native networking. CI checks Python 3.12 on Linux, Windows and macOS, plus Python 3.14 on Linux, and exercises the native Tk GUI on all three operating systems. The Linux integration job tests real speech, FFmpeg encoders and player JavaScript, and builds wheel/source artifacts. QuickJS is used only for player tests and is not an app dependency. Verified voice and dependency caches avoid repeated downloads. No private book or narration is uploaded by CI.

The `audiopod-narration-comparison` CI artifact contains Original/Natural WAVs of the public `examples/voice-check.md` sample and a measurement report for listening review. QEC's decoder work informs strict validation and evidence handling; its syndrome decoder is not used as a speech model. See [the engine notes](docs/NATURAL_NARRATION.md#what-qec-contributes) for exact source references and limits.

AudioPod source is Apache-2.0. Third-party dependencies, engines, voices and user books retain their own licences. See [THIRD_PARTY.md](THIRD_PARTY.md).
