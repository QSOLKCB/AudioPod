# Natural narration

[Getting started](GETTING_STARTED.md) · [Home](../README.md)

AudioPod's **Natural** delivery mode improves how local Piper speech is planned, joined and levelled. The trained voice still determines pronunciation, timbre and much of the intonation. No mathematical test can certify that a synthetic reading is maximally natural for every listener, language or book. Preview names, dialogue and emotional passages before publishing an audiobook.

## Choose a delivery

New jobs default to **Natural**. The desktop's **Delivery** control switches between Natural and Original. **Pause length** adjusts Natural's supplemental pauses from 0.5× to 2×; speech speed remains a separate control. These settings also apply to voice previews and are remembered locally.

```sh
uv run --offline --locked audiopod render book.epub --output output/natural \
  --style natural --speed 1.0 --pause-scale 1.0

uv run --offline --locked audiopod render book.epub --output output/original \
  --style original
```

Original retains the earlier chunking, Piper sentence peak normalization and fixed 120 ms padding. Use it for comparisons or to continue older jobs. It has no adjustable pause length.

**Resume folder…** and `audiopod resume` restore the saved delivery automatically. Jobs created before this feature restore Original. If using `render ... --resume` manually, repeat every original setting, including `--style original` for an older job. Switching style or pause length requires a new output folder; completed chapters are never silently mixed between renderers. Natural's versioned profile, `natural-v1`, is part of the hashed job identity. Original preserves the previous four-field settings identity.

## What the engine does

1. Plan bounded phrases at sentence and paragraph boundaries. Recognize common English titles, dotted acronyms, decimal points, Unicode sentence punctuation and quoted questions followed by attribution. Long sentences prefer clause boundaries, then whitespace; an unbroken token has a hard 600-character bound. Every non-whitespace source character is retained. This is a conservative planner, not a full multilingual grammar parser.
2. Phonemize each planned phrase and keep its subgroups in one inference context. All returned phonemes and punctuation remain in order. Retain the voice's trained duration/noise defaults, scaling duration only for the requested speech speed. Reject empty speech or excessive symbol sequences. No random pitch wobble, invented emphasis or text rewriting is added.
3. Use the model's raw floating-point waveform. Piper's default synthesis normalizes each sentence independently; Natural defers level adjustment until the whole chapter is available. This preserves relative phrase levels supplied by the voice.
4. Remove each phrase's mean DC offset and apply a 3 ms raised-cosine fade at its endpoints. Sample count and order are unchanged. The fades bring splice endpoints to zero, reducing discontinuities without cutting off samples or overlapping speech.
5. Add only the quiet time still needed at a boundary. Baseline targets are 280 ms between sentences, 500 ms between paragraphs, 140 ms at a forced clause split, zero at a forced continuation, and 180 ms after the last phrase. Existing leading/trailing quiet samples count toward the target. Audio is never trimmed when existing quiet time is longer. Targets scale by pause length / speech speed.
6. Apply one gain to the whole chapter, write PCM16 WAV, then reopen it and independently check its format, frame count, non-silence and sample peak before publishing or encoding it.

The pause calculation is `max(0, target_frames - previous_quiet_tail - next_quiet_lead)`. Quiet-edge detection uses 0.1% of that phrase's peak (with a very small numerical floor); it is only used to decide additional silence. All model samples remain in the output.

The chapter gain is:

```text
gain = min(4, 0.1 / source_rms, 10**(-1/20) / source_peak)
```

The RMS target is −20 dBFS, maximum boost is about +12 dB, and PCM sample-peak ceiling is −1 dBFS, subject to PCM16 rounding. RMS used to choose gain includes model-generated quiet samples but excludes newly inserted pauses, so changing pause length cannot change the gain. The peak ceiling takes priority over reaching the RMS target. There is no dynamic compressor or hard clipping in this stage.

These are **sample-peak and RMS measurements**, not true-peak limiting, LUFS loudness normalization or a perceptual quality score. MP3/AAC encoding can change waveform peaks. The `pcm_quality` record in each completed chapter explicitly describes the **pre-encoding PCM WAV**. It is informational; completed-audio hashes remain the authority for resume checks. Receipts are local consistency records, not signed attestations.

## What QEC contributes

The review inspected QSOLKCB/QEC at commit [`27bbc798c4e38138ca5b0fff70b15c3271a1917d`](https://github.com/QSOLKCB/QEC/tree/27bbc798c4e38138ca5b0fff70b15c3271a1917d), including:

- `docs/QUTRIT_HARMONIC_QEC.md`: bounded GF(3) syndrome/coset-leader decoding.
- `docs/ACOUSTIC_SYNDROME_BRIDGE.md` and `src/qec/experiments/acoustic/channel.py`: explicitly encoded acoustic symbols, strict PCM handling and independently checked decoded observations.
- `src/qec/experiments/acoustic/_common.py` and `src/qec/decoder/energy.py`: finite-value checks, evidence boundaries and decoder-specific objectives.

Those decoders recover deliberately encoded symbols under a defined code/channel model. Ordinary synthesized narration has no such code or syndrome, and decoder energy is not a speech-naturalness objective. AudioPod therefore applies the useful engineering principles: reject non-finite/malformed signals, bound resource use, recompute measurements from finished PCM, preserve source samples, and keep renderer identity and claims explicit.

No QEC implementation is copied or installed. The integration is at the validation/design level; it does not claim quantum audio enhancement, error-corrected pronunciation or improved speech from a syndrome decoder. There are no new runtime dependencies. AudioPod's existing source licence and the separate voice/engine licences remain unchanged.

## Compare and verify locally

Install the voice once, then use the supplied original public text:

```sh
uv run --offline --locked python scripts/compare_narration.py \
  --output output/narration-comparison
```

Open `original/listen.html` and `natural/listen.html` inside that folder. Compare phrasing and joins at a comfortable listening volume: Original's higher level can bias a preference judgment. The JSON report includes both exact source/model/runtime/settings identities, final WAV hashes, measured levels and elapsed rendering times. Neural inference is stochastic, so differences between two full renders are not an isolated DSP experiment. The signal regression tests instead feed identical fixed waveforms to the conditioning stage.

One executed local run on 2026-11-04 UTC used Cori UK English medium, Python 3.12.14, Piper 1.8.0, ONNX Runtime 1.31.1, NumPy 2.5.4 and four inference threads on a Linux x86_64 host reporting nine logical CPUs:

| Measurement | Original | Natural |
| --- | ---: | ---: |
| Audio duration | 23.32 s | 25.02 s |
| Render time, including model verification/loading | 3.03 s | 3.12 s |
| PCM sample peak | 0.00 dBFS | −2.46 dBFS |
| PCM RMS, including all pauses | −14.47 dBFS | −20.50 dBFS |
| Full-scale PCM samples | 10 | 0 |

Natural retained all 491,264 model samples and added 60,463 pause samples, producing 551,727 frames across eight phrases. Full-scale samples in Original do not by themselves establish clipping. This small timing sample is not a speedup claim, and no blind human listening study was performed.

Executed regression coverage checks a preserved 4:1 phrase amplitude ratio, zero splice endpoints, finite output and peak bounds, exact source-plus-padding frame accounting, quiet-edge credit, pause-independent gain, cancellation, malformed inference audio, truncated/changed WAVs, and saved-job identity separation. A completed pre-feature speech job resumed with both original WAV hashes unchanged and without loading the engine. Native Tk smoke tests exercise delivery/pause preferences and restoring both styles.

CI runs the signal tests with the locked speech dependencies, real Cori narration with native network tracing, and native desktop tests on Linux, Windows and macOS. The **audiopod-narration-comparison** workflow artifact contains only the repository's public sample, both renders, players and measurements; it is retained for 14 days. CI does not upload user books or private audio.

## Resources and limits

The model still loads once per job. Planning scans bounded windows rather than repeatedly copying the remainder of a chapter. Conditioning and verification are vectorized and stream the finished chapter in blocks. A local planner check processed 1,950,003 characters / 60,000 phrases in 3.43 seconds with tracing enabled and about 19 KiB peak traced allocation after constructing the source text; this measures the planner alone, not inference or total process memory.

Natural needs a temporary float32 spool for each unfinished chapter, about twice its PCM16 WAV size, plus the WAV while finalizing. The spool closes after verification; MP3/M4B may need additional encoding space. A chapter must stay below the existing 3.9 GB PCM limit, including inserted pauses. Shorter source chapters reduce temporary storage and cancellation/restart cost. Memory remains bounded by a phrase's inference output and processing blocks; the full chapter waveform is not held in RAM.

Other voice models and languages can respond differently to phrase planning. Preview them, use Original if preferred, and report the voice/config hashes with any repeatable pronunciation or timing defect. Actual speech inference has been exercised with Cori on Linux; desktop tests on the other platforms do not establish native speech-quality equivalence.
