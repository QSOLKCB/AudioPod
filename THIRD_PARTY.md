# Engine and voice provenance

AudioPod source is Apache-2.0. This repository contains no Piper binaries, voice weights or user books. The AudioPod wheel contains the app, not its dependency binaries. Third-party components retain their applicable licences and notices; AudioPod's licence does not relicense them.

## Piper

- Project: [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl).
- Runtime: **1.8.0**, pinned in `pyproject.toml` and `uv.lock`.
- Upstream: GPL-3.0. Piper includes an eSpeak NG phonemizer; consult the upstream distribution notices too.
- AudioPod uses CPU ONNX inference. It does not enable CUDA, model patching, training, automatic Arabic diacritization or phonemizers requiring further language downloads.
- The lockfile records resolved dependencies, distribution URLs and hashes. Those packages have their own licences.
- ONNX Runtime telemetry is opted out before native initialization using `ORT_DISABLE_TELEMETRY=1`, with API suppression as a second measure. See the upstream [privacy documentation](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md).

## Default voice: Cori medium

- Repository: [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- Immutable revision: `e7229f7d33a10e145e109b886d661984201ac3c4`.
- Directory: `en/en_GB/cori/medium`.
- [Model card](https://huggingface.co/rhasspy/piper-voices/blob/e7229f7d33a10e145e109b886d661984201ac3c4/en/en_GB/cori/medium/MODEL_CARD): UK English, one female speaker, 22,050 Hz, medium quality. It identifies a public-domain LibriVox dataset, training from scratch, and Bryce Beattie's TTS work. The card is retained with installed voice files. This is provenance, not a new licence grant for the voice.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `en_GB-cori-medium.onnx` | 63,531,379 | `1899f98e5fb8310154f3c2973f4b8a929ba7245e722b3d3a85680b833d95f10d` |
| `en_GB-cori-medium.onnx.json` | 4,966 | `e262c16d7f192f69d4edd6b4ef8a5915379e67495fcc402f1ab15eeb33da3d36` |
| `MODEL_CARD` | 474 | `38d76dfde845837b184668f8bab1c6426ad740b1af0fcebc349037822739e536` |

Alternative voices may have different terms, including non-commercial restrictions. Review their model cards before distributing generated audio. AudioPod does not clone a supplied person's voice.

## FFmpeg and content

MP3/M4B encoding invokes the user's installed [FFmpeg](https://ffmpeg.org/legal.html), whose licence depends on its build. AudioPod does not redistribute it. WAV needs no FFmpeg.

The original text in `examples/first-listen.md` is under this repository's Apache-2.0 licence. User books remain their rights holders' property. Full selected text is included in the local listening page; consider that when sharing an output folder.
