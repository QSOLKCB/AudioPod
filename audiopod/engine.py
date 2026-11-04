"""One CPU model session per render; no network or downloads."""

import os
import math
import wave

from . import AudioPodError, Cancelled
from .books import split_text
from .prosody import NATURAL, ORIGINAL, PAUSE_SECONDS, phrases


class PiperEngine:
    def __init__(self, model, config, speed=1.0, speaker=0, threads=4, profile=NATURAL, pause_scale=1.0):
        if profile not in (NATURAL, ORIGINAL) or type(pause_scale) not in (int, float) or not .5 <= pause_scale <= 2:
            raise AudioPodError("Choose a supported narration style and pause scale between 0.5 and 2.")
        self.profile, self.pause_scale, self.speed = profile, pause_scale, speed
        try:
            import onnxruntime as ort
            ort.disable_telemetry_events()
            from piper import PiperVoice, SynthesisConfig
            from piper.config import PiperConfig
        except ImportError as exc:
            raise AudioPodError("Piper is not installed. Run uv sync --locked, then launch with uv run --offline audiopod.") from exc
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(threads, os.cpu_count() or 1))
        options.inter_op_num_threads = 1
        try:
            # Explicit thread budget avoids excessive contention on many-core CPUs.
            session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
            self.voice = PiperVoice(config=PiperConfig.from_dict(config), session=session, use_tashkeel=False)
            length_scale = 1.0 if profile == ORIGINAL else self.voice.config.length_scale
            if not math.isfinite(length_scale) or length_scale <= 0:
                raise AudioPodError("Voice has an invalid default speech duration.")
            self.settings = SynthesisConfig(length_scale=length_scale / speed, speaker_id=speaker,
                                            normalize_audio=profile == ORIGINAL)
            self.rate = config["audio"]["sample_rate"]
        except Exception as exc:
            raise AudioPodError(f"Could not load the local voice: {exc}") from exc

    def render(self, text, target, progress, cancelled):
        if self.profile == ORIGINAL:
            return self._render_original(text, target, progress, cancelled)
        from .audio import NaturalAudio
        try:
            total = sum(1 for _ in phrases(text))
            with NaturalAudio(target, self.rate, cancelled) as output:
                for index, phrase in enumerate(phrases(text)):
                    if cancelled():
                        raise Cancelled("Stopped. Completed chapters are saved.")
                    # Keep a planned sentence in one inference context, including
                    # phonemizer subgroups caused by abbreviations or dialogue.
                    # Retain every phoneme and punctuation marker in source order.
                    phonemes = [p for group in self.voice.phonemize(phrase.text) for p in group]
                    if not phonemes:
                        if any(c.isalnum() for c in phrase.text):
                            raise AudioPodError("The voice could not pronounce a phrase. Check its language and text.")
                        continue
                    ids = self.voice.phonemes_to_ids(phonemes)
                    if not ids or len(ids) > 4096:
                        raise AudioPodError("A phrase exceeds the speech-symbol limit. Split unusually long tokens or passages.")
                    samples = self.voice.phoneme_ids_to_audio(ids, self.settings)
                    pause = PAUSE_SECONDS[phrase.boundary] * self.pause_scale / self.speed
                    output.append(samples, pause)
                    progress(index + 1, total)
                progress(total, max(1, total))
                return output.finish()
        except (AudioPodError, KeyboardInterrupt):
            raise
        except Exception as exc:
            raise AudioPodError(f"Narration failed: {exc}") from exc

    def _render_original(self, text, target, progress, cancelled):
        total = sum(1 for _ in split_text(text))
        frames = padding_frames = 0
        try:
            with wave.open(str(target), "wb") as wav:
                wav.setparams((1, 2, self.rate, 0, "NONE", "not compressed"))
                for index, part in enumerate(split_text(text)):
                    if cancelled():
                        raise Cancelled("Stopped. Completed chapters are saved; resume restarts the unfinished chapter.")
                    for audio in self.voice.synthesize(part, syn_config=self.settings):
                        if cancelled():
                            raise Cancelled("Stopped. Completed chapters are saved.")
                        if (audio.sample_rate, audio.sample_width, audio.sample_channels) != (self.rate, 2, 1):
                            raise AudioPodError("Voice returned an unexpected audio format.")
                        data = audio.audio_int16_bytes
                        frames += len(data) // 2
                        if (frames + padding_frames) * 2 > 3_900_000_000:
                            raise AudioPodError("Chapter exceeds the WAV size limit. Split it into smaller chapters.")
                        wav.writeframesraw(data)
                    # Short separation keeps independent chunks from running together.
                    padding = int(self.rate * 0.12)
                    padding_frames += padding
                    if (frames + padding_frames) * 2 > 3_900_000_000:
                        raise AudioPodError("Chapter exceeds the WAV size limit. Split it into smaller chapters.")
                    wav.writeframesraw(b"\0\0" * padding)
                    progress(index + 1, total)
            if frames == 0:
                raise AudioPodError("The voice produced no audio for this chapter.")
        except (AudioPodError, KeyboardInterrupt):
            raise
        except Exception as exc:
            raise AudioPodError(f"Narration failed: {exc}") from exc
