import contextlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from audiopod.cli import main
from audiopod.preferences import load_preferences, save_preferences, suggested_output


class SetupTests(unittest.TestCase):
    def test_preferences_round_trip_excludes_text_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'AUDIOPOD_DATA_HOME': temp}):
            self.assertTrue(save_preferences({'model':'/local/voice.onnx', 'speed':1.25, 'threads':2, 'font_size':14, 'text':'PRIVATE BOOK'}))
            prefs = load_preferences()
            self.assertEqual((prefs['model'], prefs['speed'], prefs['threads'], prefs['font_size']), ('/local/voice.onnx', 1.25, 2, 14))
            self.assertNotIn('PRIVATE BOOK', (Path(temp) / 'preferences.json').read_text())
            (Path(temp) / 'preferences.json').write_text('{"threads": "oops", "speed": NaN}')
            self.assertEqual(load_preferences()['threads'], 4)
            self.assertEqual(load_preferences()['speed'], 1)
            (Path(temp) / 'preferences.json').write_text(json.dumps({'speed': 10 ** 400}))
            self.assertEqual(load_preferences()['speed'], 1)
            (Path(temp) / 'preferences.json').write_text('{broken')
            self.assertIsInstance(load_preferences(), dict)

    def test_output_suggestion_is_safe_and_does_not_replace_existing_book(self):
        with tempfile.TemporaryDirectory() as temp:
            first = suggested_output(temp, '../../CON: a book?')
            self.assertEqual(first.parent, Path(temp))
            self.assertTrue(first.name.startswith('audiopod-'))
            first.mkdir()
            second = suggested_output(temp, '../../CON: a book?')
            self.assertNotEqual(first, second)
            self.assertFalse(second.exists())

    def test_doctor_reports_missing_voice_without_network_or_traceback(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(socket.socket, 'connect', side_effect=AssertionError('network')):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = main(['doctor', '--model', str(Path(temp) / 'missing.onnx'), '--json'])
            report = json.loads(out.getvalue())
            self.assertEqual(result, 1)
            self.assertFalse(report['ready_for_wav'])
            self.assertTrue(any(c['name'] == 'Voice' and not c['ok'] for c in report['checks']))


if __name__ == '__main__':
    unittest.main()
