"""Measured PCM conditioning. This is classical DSP, not error-correcting decoding.

NumPy is already supplied by Piper; importing the CLI does not import it here.
No samples are trimmed, overlapped or resynthesized by this module.
"""

import math
from pathlib import Path
import tempfile
import wave

from . import AudioPodError, Cancelled
from .prosody import NATURAL

PEAK_CEILING = 10 ** (-1 / 20)
TARGET_RMS = 10 ** (-20 / 20)
MAX_GAIN = 4.0
MAX_PCM_BYTES = 3_900_000_000
BLOCK_FRAMES = 65536


def measure_wav(path, rate, expected_frames, cancelled=lambda: False):
    """Independently measure the completed canonical PCM WAV before publication."""
    import numpy as np
    count, peak, squares = 0, 0, 0.
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, rate, "NONE"):
            raise AudioPodError("Generated WAV has an unexpected audio format.")
        if wav.getnframes() != expected_frames or Path(path).stat().st_size != 44 + expected_frames * 2:
            raise AudioPodError("Generated WAV has an unexpected or truncated frame count.")
        while raw := wav.readframes(BLOCK_FRAMES):
            if cancelled():
                raise Cancelled("Audio verification cancelled. Completed chapters remain available.")
            if len(raw) % 2:
                raise AudioPodError("Generated WAV has an incomplete sample.")
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float64)
            count += len(samples)
            peak = max(peak, int(np.max(np.abs(samples))))
            squares += float(np.dot(samples, samples))
    if count != expected_frames or not count or peak == 0:
        raise AudioPodError("Generated WAV is truncated or contains no audible samples.")
    if peak > round(PEAK_CEILING * 32767):
        raise AudioPodError("Generated WAV exceeded the natural pipeline's sample-peak ceiling.")
    return {"frames": count, "sample_rate": rate, "sample_peak_dbfs": 20 * math.log10(peak / 32767),
            "rms_dbfs": 10 * math.log10(squares / count / (32767 ** 2)), "clipped_samples": 0}


class NaturalAudio:
    """Spool bounded float chunks, then apply one gain to the entire chapter."""

    def __init__(self, target, rate, cancelled=lambda: False):
        import numpy as np
        self.np, self.target, self.rate, self.cancelled = np, Path(target), rate, cancelled
        if type(rate) is not int or not 8000 <= rate <= 96000:
            raise AudioPodError("Voice returned an unsupported sample rate.")
        self.raw = tempfile.TemporaryFile(dir=self.target.parent)
        self.frames = self.source_frames = self.padding_frames = self.chunks = 0
        self.peak = self.squares = self.max_dc = 0.
        self.previous_tail = 0
        self.previous_pause = 0.

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.raw.close()

    def _check_cancel(self):
        if self.cancelled():
            raise Cancelled("Stopped. Completed chapters are saved; resume restarts the unfinished chapter.")

    def _reserve(self, frames):
        if (self.frames + frames) * 2 > MAX_PCM_BYTES:
            raise AudioPodError("Chapter exceeds the WAV size limit. Split it into smaller chapters.")
        self.frames += frames

    def _silence(self, frames):
        self._reserve(frames)
        self.padding_frames += frames
        while frames:
            self._check_cancel()
            take = min(frames, BLOCK_FRAMES)
            self.raw.write(b"\0" * (take * 4))
            frames -= take

    def append(self, samples, pause_after):
        np = self.np
        self._check_cancel()
        if type(pause_after) not in (int, float) or not 0 <= pause_after <= 4:
            raise AudioPodError("Invalid planned pause duration.")
        values = np.asarray(samples)
        if values.ndim != 1 or not values.size or values.dtype.kind != "f" or not np.all(np.isfinite(values)):
            raise AudioPodError("Voice returned empty, non-finite or malformed audio.")
        if float(np.max(np.abs(values))) > float(np.finfo(np.float32).max) / 2:
            raise AudioPodError("Voice samples exceed the supported float range.")
        values = np.array(values, dtype=np.float32, copy=True)
        dc = float(np.mean(values, dtype=np.float64))
        values -= dc
        self.max_dc = max(self.max_dc, abs(dc))
        # A 3 ms raised-cosine envelope makes splice endpoints exactly zero.
        fade = min(round(self.rate * .003), len(values) // 2)
        if fade >= 2:
            ramp = (.5 - .5 * np.cos(np.linspace(0, math.pi, fade))).astype(np.float32)
            values[:fade] *= ramp
            values[-fade:] *= ramp[::-1]
        peak = float(np.max(np.abs(values)))
        if peak < 1e-7:
            raise AudioPodError("Voice returned silent or DC-only audio for a phrase.")
        active = np.flatnonzero(np.abs(values) > max(1e-9, peak * .001))
        leading, trailing = int(active[0]), len(values) - int(active[-1]) - 1
        if self.chunks:
            # Existing model silence counts toward the pause. Nothing is trimmed.
            self._silence(max(0, round(self.previous_pause * self.rate) - self.previous_tail - leading))
        self._reserve(len(values))
        self.raw.write(values.astype("<f4", copy=False).tobytes())
        self.source_frames += len(values)
        self.peak = max(self.peak, peak)
        wide = values.astype(np.float64)
        self.squares += float(np.dot(wide, wide))
        self.previous_tail, self.previous_pause = trailing, pause_after
        self.chunks += 1

    def finish(self):
        self._check_cancel()
        if not self.source_frames or self.peak <= 0:
            raise AudioPodError("The voice produced no audio for this chapter.")
        self._silence(max(0, round(self.previous_pause * self.rate) - self.previous_tail))
        # RMS excludes inserted pauses, so changing pause length cannot pump gain.
        rms = math.sqrt(self.squares / self.source_frames)
        gain = min(MAX_GAIN, TARGET_RMS / rms, PEAK_CEILING / self.peak)
        self.raw.seek(0)
        np = self.np
        with wave.open(str(self.target), "wb") as wav:
            wav.setparams((1, 2, self.rate, 0, "NONE", "not compressed"))
            while raw := self.raw.read(BLOCK_FRAMES * 4):
                self._check_cancel()
                values = np.frombuffer(raw, dtype="<f4").astype(np.float64)
                quantized = np.rint(values * (gain * 32767))
                if not np.all(np.isfinite(quantized)) or np.max(np.abs(quantized)) > round(PEAK_CEILING * 32767):
                    raise AudioPodError("PCM conversion failed its finite-range check.")
                wav.writeframesraw(quantized.astype("<i2").tobytes())
        measured = measure_wav(self.target, self.rate, self.frames, self.cancelled)
        return {"pipeline": NATURAL, "measurement": "pre-encoding PCM WAV",
                "source_frames": self.source_frames, "pause_frames_added": self.padding_frames,
                "phrases": self.chunks, "gain_db": 20 * math.log10(gain),
                "maximum_dc_removed": self.max_dc, **measured}
