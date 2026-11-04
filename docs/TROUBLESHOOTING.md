# Troubleshooting and recovery

[Installation](INSTALLATION.md) · [Getting started](GETTING_STARTED.md) · [Home](../README.md)

Start with `uv run --offline --locked audiopod doctor`, or **Help & accessibility → Check setup**. This reads local prerequisites and voice hashes; it does not install anything or test an actual display. Follow with a short voice preview.

| Symptom | What to do |
| --- | --- |
| `uv` or `git` not found | Install the tool, then reopen the terminal so PATH is refreshed. |
| Missing Piper/dependencies | Run `uv sync --locked` in the checkout, then use `uv run --offline --locked audiopod`. |
| Missing Tk | Install Tk for the exact Python used by uv. On Ubuntu use `python3-tk` and sync with `/usr/bin/python3`; on Homebrew use matching Python/Tk formula versions. Test with `uv run --offline python -m tkinter`. |
| Cannot open display | A graphical desktop is required for the GUI. Use the CLI in SSH/headless environments. |
| Missing voice | Use the explicit Install Cori action, or choose a local `.onnx` with its adjacent `.onnx.json`. |
| Download/hash check failed | Check your connection and retry voice installation. Verified files are reused; a corrupt/incomplete download is not installed. Do not bypass the hash check. |
| Missing MP3/M4B encoder | Install FFmpeg with `libmp3lame`/`aac` on PATH, restart the app, or use WAV. The setup check lists encoder availability. |
| Input is rejected | Use DRM-free EPUB or UTF-8 TXT/Markdown. Directories, devices and named pipes are rejected. PDF, DOCX and OCR are not supported. |
| Encrypted EPUB resources | Export a plain DRM-free EPUB/TXT from your source. Font obfuscation/encrypted resources also trigger rejection; AudioPod does not remove encryption. |
| Output folder is not empty | Pick a new suggested folder, or use Resume folder with the original source. |
| Resume says different text/settings | Restore the saved options using Resume folder or the `resume` command. Use the original source, voice and runtime; changed inputs require a new output folder. |
| Saved audio is missing or changed | Preserve the original output folder. Restore an exact backup or render to a new folder. Do not edit hashes to hide a mismatch. |
| Cancel seems delayed | A synthesis chunk or current network read must return before cancellation takes effect. The GUI stays responsive. Closing during work requests the same safe stop. |
| Incorrect pronunciation | Try a matching-language voice, another speaker, or slower speed. Review invented names. AudioPod does not rewrite the book to guess pronunciations. |
| Browser bookmark does not persist | Some browsers restrict local-file storage. Keep the same folder/browser, use the native audio files, or use an audiobook player with its own bookmarks. |
| Old audio opens after changing books | New imports now clear the previous Listen target. Choose the new job's Listen control after creating audio. |
| Preferences seem wrong | Close the app, move `preferences.json` aside in its data folder, then reopen. Invalid preference files fall back to defaults. Audiobooks are separate. |

## Recovery after a forced stop or power loss

1. Confirm that no AudioPod render is still using the output folder. Normal Cancel removes its lock automatically.
2. Make a backup of the output folder before manual recovery.
3. Remove the empty `.audiopod-lock` directory left by the interrupted process.
4. Reopen the exact source and choose Resume folder, or run the CLI `resume` command.
5. If an untracked audio file is reported, a crash may have occurred between its final rename and receipt write. Move only that reported file aside; then resume. AudioPod will regenerate that unfinished section.

Temporary `.chapter-*`, `.encode-*` and `.write-*` leftovers can be removed when no job is running. Keep numbered audio files, `book.m4b`, `audiopod.json`, `listen.html` and the playlist. Resume validates **all** tracked audio before producing more audio or rewriting the player.

Do not remove a live lock or run two processes in the same output folder. A lock is not automatically expired, because a long synthesis can legitimately take time. Filesystem edits by another process during a render are unsupported.

## Disk space and long books

M4B rendering needs the chapter WAVs and the final compressed audiobook at the same time. Provide several times the expected compressed size in free space. The app refuses oversized input/archive entries and stops WAV chapters before the RIFF limit. Split an exceptionally long single section into smaller source sections.

The displayed audio-length estimate assumes approximately 160 words/minute at normal voice speed. Actual voice delivery varies. Processing time depends on CPU, model, text and encoding; the estimate is not a completion-time promise.

## Reporting a reproducible issue

Include the app commit/version, OS, Python version, output format, exact error and a `doctor --json` report with any private paths removed. Provide the smallest synthetic text/EPUB that reproduces the issue and describe expected versus observed behaviour. Do not post a private book, generated narration, voice weights or credentials in a public issue.
