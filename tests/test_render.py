from dataclasses import replace
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from audiopod import AudioPodError, Cancelled
from audiopod.books import Book, Chapter
from audiopod.player import player_html
from audiopod.render import Settings, render_book
from audiopod.voices import inspect_model, install_voice, FILES, default_model


class ToneEngine:
    calls = 0
    loads = 0

    def __init__(self, *args):
        ToneEngine.loads += 1

    def render(self, text, target, progress, cancelled):
        ToneEngine.calls += 1
        if cancelled():
            raise Cancelled('cancelled')
        with wave.open(str(target), 'wb') as wav:
            wav.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            wav.writeframes(b''.join(struct.pack('<h', round(12000 * math.sin(i / 12))) for i in range(2205)))
        progress(1, 1)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.model = self.root / 'voice.onnx'
        self.model.write_bytes(b'test-only model; ToneEngine replaces inference')
        Path(str(self.model) + '.json').write_text(json.dumps({'audio': {'sample_rate': 22050}, 'num_speakers': 1, 'phoneme_type': 'espeak'}))
        self.book = Book('Test Book', 'Author', 'en', (Chapter('One', 'Hello.'), Chapter('Two', 'Goodbye.')), 'source-digest')
        self.output = self.root / 'output'
        ToneEngine.calls = ToneEngine.loads = 0

    def tearDown(self):
        self.temp.cleanup()

    def render(self, **kwargs):
        return render_book(self.book, self.model, self.output, engine_factory=ToneEngine, **kwargs)

    def test_wav_export_and_verified_resume_reuses_one_model(self):
        player = self.render()
        self.assertTrue(player.is_file())
        self.assertEqual(ToneEngine.loads, 1)
        self.assertEqual(ToneEngine.calls, 2)
        self.render(resume=True)
        self.assertEqual(ToneEngine.calls, 2)
        self.assertEqual(ToneEngine.loads, 1)
        manifest = json.loads((self.output / 'audiopod.json').read_text())
        self.assertEqual(len(manifest['completed']), 2)
        self.assertEqual((self.output / 'playlist.m3u').read_text(), '#EXTM3U\n0001.wav\n0002.wav\n')

    def test_changed_text_voice_and_settings_cannot_resume(self):
        self.render()
        self.book = replace(self.book, chapters=(Chapter('One', 'Changed.'), self.book.chapters[1]))
        with self.assertRaisesRegex(AudioPodError, 'different'):
            self.render(resume=True)
        self.book = replace(self.book, chapters=(Chapter('One', 'Hello.'), self.book.chapters[1]))
        with self.assertRaisesRegex(AudioPodError, 'different'):
            self.render(resume=True, settings=Settings(speed=1.2))
        self.model.write_bytes(b'changed model')
        with self.assertRaisesRegex(AudioPodError, 'different'):
            self.render(resume=True)

    def test_corrupted_completed_audio_is_not_reused(self):
        self.render()
        (self.output / '0001.wav').write_bytes(b'corrupt')
        with self.assertRaisesRegex(AudioPodError, 'missing or changed'):
            self.render(resume=True)
        self.assertEqual(ToneEngine.calls, 2)

    def test_no_overwrite_and_lock_exclusion(self):
        self.output.mkdir()
        (self.output / 'important.txt').write_text('keep me')
        with self.assertRaisesRegex(AudioPodError, 'not empty'):
            self.render()
        self.assertEqual((self.output / 'important.txt').read_text(), 'keep me')
        (self.output / '.audiopod-lock').mkdir()
        with self.assertRaisesRegex(AudioPodError, 'locked'):
            self.render()

    def test_cancel_keeps_completed_chapter_then_resume(self):
        stop = [False]
        def progress(event):
            if event['fraction'] >= 0.5:
                stop[0] = True
        with self.assertRaises(Cancelled):
            self.render(progress=progress, cancelled=lambda: stop[0])
        self.assertTrue((self.output / '0001.wav').is_file())
        self.assertFalse((self.output / '0002.wav').exists())
        self.assertFalse((self.output / '.audiopod-lock').exists())
        self.render(resume=True)
        self.assertEqual(ToneEngine.calls, 2)

    def test_failure_during_chapter_keeps_no_partial_audio(self):
        class BrokenEngine(ToneEngine):
            def render(self, text, target, progress, cancelled):
                Path(target).write_bytes(b'partial')
                raise AudioPodError('engine failed')
        with self.assertRaisesRegex(AudioPodError, 'engine failed'):
            render_book(self.book, self.model, self.output, engine_factory=BrokenEngine)
        self.assertFalse((self.output / '0001.wav').exists())
        self.assertFalse(list(self.output.glob('.chapter-*')))
        self.render(resume=True)
        self.assertEqual(ToneEngine.calls, 2)

    def test_selection_and_numeric_safe_filenames(self):
        self.book = replace(self.book, chapters=(Chapter('../../outside', 'Hello.'), Chapter('Other', 'World.')))
        self.render(selected=[1])
        self.assertFalse((self.output / '0001.wav').exists())
        self.assertTrue((self.output / '0002.wav').is_file())
        for selected in [[], [-1], [2]]:
            with self.subTest(selected=selected), self.assertRaises(AudioPodError):
                self.render(selected=selected)

    def test_invalid_settings_and_missing_model(self):
        for settings in [Settings(speed=float('nan')), Settings(speed=0), Settings(threads=0), Settings(format='exe'), Settings(speaker=1)]:
            with self.subTest(settings=settings), self.assertRaises(AudioPodError):
                self.render(settings=settings)
        self.model.unlink()
        with self.assertRaises(AudioPodError):
            self.render()

    def test_missing_ffmpeg_is_detected_before_output(self):
        with patch('audiopod.render.shutil.which', return_value=None), self.assertRaisesRegex(AudioPodError, 'FFmpeg'):
            self.render(settings=Settings(format='mp3'))
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/ffprobe are optional')
    def test_mp3_and_m4b_chapters_decode(self):
        import subprocess
        for fmt in ['mp3', 'm4b']:
            with self.subTest(fmt=fmt):
                self.output = self.root / fmt
                self.render(settings=Settings(format=fmt))
                target = self.output / ('book.m4b' if fmt == 'm4b' else '0001.mp3')
                result = subprocess.run(['ffprobe', '-v', 'error', '-show_chapters', '-show_format', '-of', 'json', str(target)], check=True, capture_output=True, text=True)
                info = json.loads(result.stdout)
                self.assertGreater(float(info['format']['duration']), 0)
                if fmt == 'm4b':
                    self.assertEqual([c['tags']['title'] for c in info['chapters']], ['One', 'Two'])
                self.render(settings=Settings(format=fmt), resume=True)

    def test_malformed_resume_manifest(self):
        self.output.mkdir()
        (self.output / 'audiopod.json').write_text('{')
        with self.assertRaises(AudioPodError):
            self.render(resume=True)
        self.assertFalse((self.output / '.audiopod-lock').exists())

    @unittest.skipIf(__import__('sys').platform == 'win32', 'Symlinks may require Windows developer mode')
    def test_symlink_output_is_rejected(self):
        real = self.root / 'real'
        real.mkdir()
        self.output.symlink_to(real, target_is_directory=True)
        with self.assertRaises(AudioPodError):
            self.render()
        self.assertEqual(list(real.iterdir()), [])

    def test_player_escapes_book_and_track_content(self):
        html = player_html('<script>alert(1)</script>', 'A & B', [{'file': '0001.wav', 'title': '</script><img src=x>', 'text': '<svg onload=alert(1)>'}], 'abc')
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('</script><img', html)
        self.assertNotIn('<svg onload=', html)
        self.assertIn('connect-src \'none\'', html)

    def test_non_espeak_voice_cannot_trigger_phonemizer_download(self):
        Path(str(self.model) + '.json').write_text(json.dumps({'phoneme_type': 'pinyin'}))
        with self.assertRaisesRegex(AudioPodError, 'offline'):
            inspect_model(self.model)


class DownloadTests(unittest.TestCase):
    def test_bad_download_is_not_installed(self):
        import io
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'AUDIOPOD_DATA_HOME': temp}):
            with patch('audiopod.voices.urllib.request.urlopen', return_value=io.BytesIO(b'corrupted')), self.assertRaisesRegex(AudioPodError, 'SHA-256'):
                install_voice()
            self.assertFalse(default_model().exists())
            self.assertFalse(list(Path(temp).rglob('.download-*')))

    def test_cancelled_download_cleans_temporary_file(self):
        import io
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'AUDIOPOD_DATA_HOME': temp}):
            with patch('audiopod.voices.urllib.request.urlopen', return_value=io.BytesIO(b'data')), self.assertRaises(Cancelled):
                install_voice(cancelled=lambda: True)
            self.assertFalse(default_model().exists())
            self.assertFalse(list(Path(temp).rglob('.download-*')))


if __name__ == '__main__':
    unittest.main()
