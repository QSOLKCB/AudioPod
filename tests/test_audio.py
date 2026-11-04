import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from audiopod import AudioPodError, Cancelled
from audiopod.audio import NaturalAudio, PEAK_CEILING, measure_wav

HAS_NUMPY = importlib.util.find_spec('numpy') is not None
if HAS_NUMPY:
    import numpy as np


@unittest.skipUnless(HAS_NUMPY, 'DSP tests run with the locked speech dependencies')
class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'chapter.wav'
        self.rate = 16000
        self.tone = (.1 * np.sin(2 * math.pi * 400 * np.arange(1600) / self.rate)).astype(np.float32)

    def tearDown(self):
        self.temp.cleanup()

    def render(self, chunks):
        with NaturalAudio(self.path, self.rate) as audio:
            for samples, pause in chunks:
                audio.append(samples, pause)
            result = audio.finish()
        with wave.open(str(self.path)) as wav:
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').copy()
        return result, pcm

    def test_common_gain_preserves_phrase_dynamics_and_frame_count(self):
        result, pcm = self.render([(self.tone, 0), (self.tone * .25, 0)])
        first, second = pcm[100:1500].astype(float), pcm[1700:3100].astype(float)
        ratio = np.sqrt(np.mean(first ** 2) / np.mean(second ** 2))
        self.assertAlmostEqual(ratio, 4, places=2)
        self.assertEqual(result['source_frames'], 3200)
        self.assertEqual(result['pause_frames_added'], 0)
        self.assertEqual(result['frames'], 3200)
        self.assertTrue(all(pcm[i] == 0 for i in (0, 1599, 1600, 3199)))
        self.assertLessEqual(np.abs(pcm.astype(float)).max(), round(PEAK_CEILING * 32767))

    def test_quiet_edges_count_toward_pauses_without_removing_samples(self):
        # Exactly zero-mean content preserves these deliberately supplied quiet edges.
        phrase = np.concatenate((np.zeros(800), self.tone, np.zeros(800))).astype(np.float32)
        short, _ = self.render([(phrase, .1), (phrase, 0)])
        longer, _ = self.render([(phrase, .2), (phrase, 0)])
        self.assertEqual(short['pause_frames_added'], 0)
        self.assertEqual(longer['source_frames'], 6400)
        self.assertGreater(longer['pause_frames_added'], 1500)
        self.assertLessEqual(longer['pause_frames_added'], 1600)
        self.assertEqual(longer['frames'], longer['source_frames'] + longer['pause_frames_added'])
        self.assertEqual(short['gain_db'], longer['gain_db'])

    def test_large_transient_is_scaled_without_clipping(self):
        samples = self.tone.copy()
        samples[800] = 4
        result, pcm = self.render([(samples, 0)])
        self.assertLess(result['gain_db'], 0)
        self.assertLessEqual(result['sample_peak_dbfs'], -.999)
        self.assertEqual(result['clipped_samples'], 0)
        self.assertLess(int(np.abs(pcm.astype(float)).max()), 32767)

    def test_quiet_audio_gain_is_capped(self):
        result, _ = self.render([(self.tone * .001, 0)])
        self.assertAlmostEqual(result['gain_db'], 20 * math.log10(4))

    def test_invalid_inference_audio_is_rejected(self):
        cases = [np.array([]), np.array([float('nan'), 0.]), np.array([float('inf'), 1.]),
                 np.ones(100), np.zeros(100), np.array([[.1, -.1]]), np.array([1, -1]),
                 np.array([1e100, -1e100])]
        for samples in cases:
            with self.subTest(samples=str(samples)[:50]), NaturalAudio(self.path, self.rate) as audio:
                with self.assertRaises(AudioPodError):
                    audio.append(samples, .1)

    def test_invalid_rate_pause_and_empty_chapter(self):
        for rate in (True, 0, 16000.0, 999999):
            with self.assertRaises(AudioPodError):
                NaturalAudio(self.path, rate)
        with NaturalAudio(self.path, self.rate) as audio:
            for pause in (True, -.1, float('nan'), float('inf'), 5):
                with self.assertRaises(AudioPodError):
                    audio.append(self.tone, pause)
            with self.assertRaises(AudioPodError):
                audio.finish()

    def test_size_limit_includes_padding_and_cancellation_is_preserved(self):
        with NaturalAudio(self.path, self.rate) as audio, patch('audiopod.audio.MAX_PCM_BYTES', 3300):
            audio.append(self.tone, 1)
            with self.assertRaisesRegex(AudioPodError, 'size limit'):
                audio.finish()
        stopped = [False]
        with NaturalAudio(self.path, self.rate, lambda: stopped[0]) as audio:
            audio.append(self.tone, 0)
            stopped[0] = True
            with self.assertRaises(Cancelled):
                audio.finish()
        self.assertTrue(audio.raw.closed)

    def test_verifier_reads_finished_pcm_and_rejects_damage(self):
        result, _ = self.render([(self.tone, 0)])
        measured = measure_wav(self.path, self.rate, len(self.tone))
        for field, value in measured.items():
            self.assertEqual(result[field], value)
        original = self.path.read_bytes()
        for damaged in (original[:-2], original + b'junk'):
            self.path.write_bytes(damaged)
            with self.assertRaises(AudioPodError):
                measure_wav(self.path, self.rate, len(self.tone))
        self.path.write_bytes(original)
        for rate, frames in ((8000, len(self.tone)), (self.rate, len(self.tone) + 1)):
            with self.assertRaises(AudioPodError):
                measure_wav(self.path, rate, frames)
        with self.assertRaises(Cancelled):
            measure_wav(self.path, self.rate, len(self.tone), lambda: True)

    def test_verifier_rejects_silence_and_full_scale_samples(self):
        for samples in (np.zeros(100, dtype='<i2'), np.full(100, 32767, dtype='<i2')):
            with wave.open(str(self.path), 'wb') as wav:
                wav.setparams((1, 2, self.rate, 0, 'NONE', 'not compressed'))
                wav.writeframes(samples.tobytes())
            with self.assertRaises(AudioPodError):
                measure_wav(self.path, self.rate, 100)
