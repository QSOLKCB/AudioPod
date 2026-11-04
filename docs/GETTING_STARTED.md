# Getting started

[Installation](INSTALLATION.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Home](../README.md)

## Make your first listen

Launch from the installed checkout:

```sh
uv run --offline --locked audiopod
```

1. Open **Help & accessibility → Check setup**. If the voice is missing, choose **Install Cori voice…**. Confirm the one-time download. Missing MP3/M4B encoders do not prevent WAV export.
2. Choose **Open book…** and select `examples/first-listen.md` from the checkout. It is a small original two-section sample. You can also paste text.
3. Inspect the preview. Select all, none, or use Ctrl/Shift to select several sections. EPUB title pages, copyright pages and part headings may be separate selectable sections.
4. Start with **Natural** delivery and a pause length of **1.0×**. Try **Voice preview**, then **Listen** and the player's Play control. The preview uses up to 400 characters from the first selected section. Adjust speed or pauses if needed; **Original** lets you compare the earlier renderer.
5. Choose an output format and check the suggested folder. AudioPod suggests a new book-specific folder and adds a suffix if that name already exists.
6. Choose **Create audiobook**. Progress shows the current section/chunk and elapsed time. The audio-length estimate describes approximate listening time, not processing time.
7. Choose **Listen** or **Open output**. Your original book remains unchanged.

## Choose a format

| Format | Good for | Files |
| --- | --- | --- |
| WAV | Lossless audio, editing, setup without FFmpeg | One PCM WAV per selected section |
| MP3 | Smaller chapter files and broad player support | One MP3 per selected section |
| M4B | One audiobook with a chapter menu | `book.m4b`, plus retained chapter WAVs |

Every job includes `listen.html`, `playlist.m3u` and `audiopod.json`. Keep the HTML player beside its chapter audio files. The M4B file can be copied independently to an audiobook player. The HTML file includes selected chapter text, so sharing a whole output folder also shares that text.

## Cancel and continue later

Click **Cancel** or press Escape. A currently synthesizing chunk finishes before stopping; completed chapters are kept. The player is refreshed on cancellation, so those chapters can be listened to immediately. If the same window remains open, **Resume this folder** is selected automatically when a job manifest exists.

After reopening the app, open the **same source book**, then choose **Resume folder…** and the original output folder. AudioPod restores the saved title, author, selection, speed, speaker, CPU threads, format, delivery and pauses. Older jobs restore **Original** delivery automatically. Select the original local voice if necessary, then choose **Create audiobook**. Every completed chapter is verified before anything is written. An unfinished chapter starts again from its beginning.

Pasted text must be pasted identically to resume; saving it as a UTF-8 `.txt` file first makes long jobs easier to reproduce. Changed source bytes, voice/configuration, runtime or settings require a new output folder. See the recovery guide before modifying a job folder after a power loss.

## Listening controls

- Play/pause and volume use the browser's native audio controls.
- Choose sections directly, move Previous/Next, or seek ±15 seconds.
- Playback speed ranges from 0.5× to 2× and does not require re-rendering.
- The sleep timer pauses playback after 5, 15, 30 or 60 minutes. It resets when the page is reopened.
- **Start book again** resets to the first section, paused.
- Expand **Read the current chapter** to read along. This is a chapter text view, not synchronized word highlighting.
- With focus outside controls, Space plays/pauses and Left/Right seek. Controls keep their normal keyboard behaviour.

Position is saved in this browser when local-file storage is available. It is restored only after audio metadata loads, so early page events cannot erase the bookmark. Moving folders, changing browsers or clearing browser data may remove bookmarks.

## Comfort and performance

Use **Help & accessibility → Larger reading text / Smaller reading text** for the section list, preview and help text. The narration controls keep their size so they remain visible. Voice, format, speed, speaker, CPU thread budget, reading text size and output parent are remembered locally. Books themselves are not restored automatically.

Start with four CPU threads. Try two on a small laptop or while doing other work; more threads are not guaranteed to be faster. The app loads a model once per render, streams bounded text chunks and keeps hash checks enabled. It batches player refreshes while preserving a receipt after every completed chapter. WAV avoids the extra encoding pass; MP3/M4B reduce final compressed file size.

Choose a voice matching the language. Cori is UK English; another trusted local eSpeak-based Piper voice can be selected with **Choose voice…**. Multi-speaker voice IDs are defined by that voice's configuration. Synthetic pronunciation and unusual names need listening review before publication.

Natural uses paragraph-aware pauses and chapter-wide levels to retain the voice's relative emphasis. Pause length changes supplemental quiet time and never trims the voice's existing audio. It also needs a temporary float32 file for the current chapter, about twice its PCM WAV size, alongside the WAV while finalizing. Read [Natural narration](NATURAL_NARRATION.md) for a public comparison sample, signal measurements, resource costs and the limits of QEC-informed validation.

## CLI examples

```sh
# Read the section list without loading the speech engine.
uv run --offline --locked audiopod inspect "My Book.epub"

# Make a small first export.
uv run --offline --locked audiopod render examples/first-listen.md --output output/first-listen

# Render selected sections with a slower voice and two CPU threads.
uv run --offline --locked audiopod render "My Book.epub" --output output/my-book \
  --chapters 2,4-7 --speed 0.9 --threads 2 --format m4b

# Restore that job's selection and settings automatically.
uv run --offline --locked audiopod resume "My Book.epub" --output output/my-book

# Check a custom local voice and save a machine-readable setup report.
uv run --offline --locked audiopod doctor --model /path/to/voice.onnx --json
```

On Windows PowerShell, put multi-line examples on one line. `resume --model` chooses a custom voice; its bytes must match the original job. The existing `render ... --resume` form also works if you repeat all original settings, including `--style original` for pre-Natural jobs. New jobs accept `--style natural --pause-scale 1.25` for longer supplemental pauses. `audiopod --help` and `audiopod render --help` list the commands/options.
