"""One CPU model session per render; no network or downloads."""

import os
import wave

from . import AudioPodError, Cancelled
from .books import split_text


class PiperEngine:
    def __init__(self, model, config, speed=1.0, speaker=0, threads=4):
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
            self.settings = SynthesisConfig(length_scale=1.0 / speed, speaker_id=speaker)
            self.rate = config["audio"]["sample_rate"]
        except Exception as exc:
            raise AudioPodError(f"Could not load the local voice: {exc}") from exc

    def render(self, text, target, progress, cancelled):
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
