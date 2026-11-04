import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from audiopod import AudioPodError, Cancelled
from audiopod.engine import PiperEngine
from audiopod.prosody import NATURAL, ORIGINAL

HAS_NUMPY = importlib.util.find_spec('numpy') is not None
if HAS_NUMPY:
    import numpy as np


class EngineConfigTests(unittest.TestCase):
    def test_natural_honours_model_timing_without_overriding_trained_noise(self):
        config = SimpleNamespace(length_scale=1.2)
        ort = SimpleNamespace(disable_telemetry_events=Mock(), SessionOptions=SimpleNamespace, InferenceSession=Mock())
        piper = SimpleNamespace(PiperVoice=Mock(return_value=SimpleNamespace(config=config)), SynthesisConfig=SimpleNamespace)
        modules = {'onnxruntime': ort, 'piper': piper,
                   'piper.config': SimpleNamespace(PiperConfig=SimpleNamespace(from_dict=lambda _: config))}
        with patch.dict('sys.modules', modules):
            natural = PiperEngine('unused.onnx', {'audio': {'sample_rate': 22050}}, speed=.8)
            original = PiperEngine('unused.onnx', {'audio': {'sample_rate': 22050}}, speed=.8, profile=ORIGINAL)
        self.assertAlmostEqual(natural.settings.length_scale, 1.5)
        self.assertFalse(natural.settings.normalize_audio)
        self.assertFalse(hasattr(natural.settings, 'noise_scale'))
        self.assertFalse(hasattr(natural.settings, 'noise_w_scale'))
        self.assertAlmostEqual(original.settings.length_scale, 1.25)
        self.assertTrue(original.settings.normalize_audio)
        self.assertEqual(ort.disable_telemetry_events.call_count, 2)


@unittest.skipUnless(HAS_NUMPY, 'Engine signal tests run with the locked speech dependencies')
class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'out.wav'
        self.engine = PiperEngine.__new__(PiperEngine)
        self.engine.profile, self.engine.pause_scale, self.engine.speed = NATURAL, 1, 1
        self.engine.rate, self.engine.settings = 16000, object()
        samples = (.1 * np.sin(np.arange(1600) * np.pi / 20)).astype(np.float32)
        self.engine.voice = SimpleNamespace(
            phonemize=Mock(return_value=[['d', '.'], ['m', '.']]),
            phonemes_to_ids=Mock(return_value=[1, 2, 3]),
            phoneme_ids_to_audio=Mock(return_value=samples),
            synthesize=Mock(side_effect=AssertionError('Unexpected per-sentence normalization path')))

    def tearDown(self):
        self.temp.cleanup()

    def render(self, text='Dr. Morgan spoke.', cancelled=lambda: False):
        return self.engine.render(text, self.path, lambda *args: None, cancelled)

    def test_planned_sentence_keeps_all_phonemes_in_one_inference_context(self):
        report = self.render()
        self.engine.voice.phonemize.assert_called_once_with('Dr. Morgan spoke.')
        self.engine.voice.phonemes_to_ids.assert_called_once_with(['d', '.', 'm', '.'])
        self.engine.voice.phoneme_ids_to_audio.assert_called_once_with([1, 2, 3], self.engine.settings)
        self.engine.voice.synthesize.assert_not_called()
        self.assertEqual(report['source_frames'], 1600)
        self.assertEqual(report['phrases'], 1)

    def test_pause_scale_and_speed_only_adjust_supplemental_pause(self):
        normal = self.render('One.\n\nTwo.')
        self.engine.pause_scale = 2
        slower_pauses = self.render('One.\n\nTwo.')
        self.assertGreater(slower_pauses['pause_frames_added'], normal['pause_frames_added'])
        self.assertEqual(slower_pauses['source_frames'], normal['source_frames'])
        self.assertEqual(slower_pauses['gain_db'], normal['gain_db'])
        self.engine.speed = 2
        faster = self.render('One.\n\nTwo.')
        self.assertEqual(faster['frames'], normal['frames'])

    def test_failed_or_unbounded_phonemization_is_actionable(self):
        self.engine.voice.phonemize.return_value = []
        with self.assertRaisesRegex(AudioPodError, 'could not pronounce'):
            self.render('Hello.')
        with self.assertRaisesRegex(AudioPodError, 'no audio'):
            self.render('...')
        self.engine.voice.phonemize.return_value = [['a']]
        self.engine.voice.phonemes_to_ids.return_value = [1] * 4097
        with self.assertRaisesRegex(AudioPodError, 'speech-symbol limit'):
            self.render()
        self.engine.voice.phoneme_ids_to_audio.assert_not_called()

    def test_inference_failure_and_cancellation_leave_no_target(self):
        self.engine.voice.phoneme_ids_to_audio.side_effect = RuntimeError('failed inference')
        with self.assertRaisesRegex(AudioPodError, 'failed inference'):
            self.render()
        self.assertFalse(self.path.exists())
        with self.assertRaises(Cancelled):
            self.render(cancelled=lambda: True)
        self.assertFalse(self.path.exists())

    def test_original_keeps_prior_pcm_and_120ms_padding(self):
        self.engine.profile = ORIGINAL
        pcm = np.arange(1, 1601, dtype='<i2').tobytes()
        self.engine.voice.synthesize = Mock(return_value=[SimpleNamespace(
            sample_rate=16000, sample_width=2, sample_channels=1, audio_int16_bytes=pcm)])
        self.assertIsNone(self.render('A sentence. Another sentence.'))
        self.engine.voice.phoneme_ids_to_audio.assert_not_called()
        with wave.open(str(self.path)) as wav:
            self.assertEqual(wav.readframes(wav.getnframes()), pcm + b'\0\0' * 1920)
