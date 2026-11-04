# Correctness and usability review

Reviewed baseline: `f905a2fd8bb83e1b5a2fe3dcb3ba2b9da3da0d8f` (merged initial app). Local validation recorded 5 November 2026. Tests use synthetic fixtures and the repository's original sample, not private books.

## Reproduced defects and regression coverage

| Trigger | Previous behaviour | Correction / executable evidence |
| --- | --- | --- |
| Split `"Hi. " + "narration " * 80` into speech chunks | The early short sentence caused a later word to be cut into `narrat` and `ion` | Prefer a later whitespace boundary; `test_short_opening_sentence_does_not_split_a_later_word` |
| EPUB adjacent table cells | Cell text joined into one word | Preserve cell boundaries; `test_epub_table_cells_and_hidden_heading_text` |
| Hidden span inside an EPUB heading | Heading title included hidden words, despite body filtering | Derive title from visible text; same EPUB regression |
| A missing unfinished chapter precedes corrupt completed audio in a resume folder | New audio/receipts could be written before later corruption was discovered | Validate the entire saved job first; byte-for-byte unchanged-folder assertion in `test_resume_validates_later_chapters_before_any_new_writes` |
| Malformed/falsey completed records | Records could be treated as unfinished chapters | Reject malformed records; `test_falsey_completed_records_are_rejected` |
| Initial browser pause/time events before audio metadata | Saved position could be overwritten with zero | Gate bookmark writes on restored metadata; actual generated JavaScript exercised by `scripts/smoke_player.py` |
| Open a new book after completing another | Listen could still open the previous book | Reset the listening target; native widget test in `scripts/smoke_gui.py` |

Regular-file checks also prevent ordinary named-pipe inputs from hanging import; the Unix regression creates a FIFO without opening it. Output locks and hash checks remain enabled. Concurrent hostile edits to a running job's filesystem are not a supported scenario.

## Measured text preparation

`scripts/benchmark_splitter.py` uses repeated plain sentences, three runs per size, and checks that all input words remain in order. On the same Linux host, Python 3.12.14, comparing the baseline splitter with this implementation:

| Characters | Chunks (both) | Baseline median | Updated median |
| ---: | ---: | ---: | ---: |
| 500,000 | 855 | 0.012347 s | 0.007033 s |
| 2,000,000 | 3,419 | 0.114481 s | 0.027862 s |
| 8,000,000 | 13,676 | 1.695286 s | 0.116284 s |

The largest fixture's text splitting was about 14.6× faster on this host. This measures preparation only, not Piper inference or total audiobook creation. The implementation indexes the original text instead of repeatedly copying its entire remaining suffix. Inference iterates bounded chunks instead of retaining every chunk string. Word counts are cached on immutable imported chapters.

The player/playlist is refreshed at most every two seconds during chapter production, then flushed on completion/cancellation/error. Every completed chapter still writes its own receipt. The 30-short-chapter regression confirms all 30 receipts/audio files while limiting full player builds to two under a fixed clock.

## Validation and limits

- 43 unit/integration tests passed locally on Python 3.12.14 and 3.14.4, including real FFmpeg MP3/M4B encode/decode tests with synthetic tones.
- Native Linux Tk tests exercised selection, preview, maximum reading size, preferences, worker completion, stale-player reset, resume controls and help. CI runs this widget test on Windows, macOS and Linux.
- QuickJS executed the generated player script for bookmark restoration, seeking, chapter advance, restart, sleep timer and unavailable/corrupt local storage. These are JavaScript behaviour tests with a minimal DOM, not browser codec or screen-reader certification.
- Real Cori inference produced two non-silent 22,050 Hz WAVs (14.57 s and 15.29 s), then verified/reused them on resume. Local execution blocked native IPv4/IPv6 socket creation through an interposer as well as Python connections. Linux CI independently traces native network syscalls.
- Native Windows/macOS speech inference still needs target-machine testing. The guides recommend a short voice preview before rendering a long book. Platform GUI checks do not establish screen-reader compatibility.

The app remains at version 0.1.0 so unchanged job identities can resume with the same installed runtime. Imports affected by corrected visible-text handling can legitimately fail an old job's text fingerprint; preserve the old output and use a new folder for changed text.
