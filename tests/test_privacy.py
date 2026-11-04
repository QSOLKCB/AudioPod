import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PrivacyTests(unittest.TestCase):
    def test_telemetry_optout_precedes_native_runtime_import(self):
        # A fresh process is required: this setting is latched by the native library.
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'onnxruntime.py').write_text('''import os
assert os.environ.get("ORT_DISABLE_TELEMETRY") == "1", "native runtime imported before telemetry opt-out"
def disable_telemetry_events():
    raise RuntimeError("opt-out reached before inference")
''')
            env = dict(os.environ, ORT_DISABLE_TELEMETRY='0')
            root = str(Path(__file__).resolve().parents[1])
            env['PYTHONPATH'] = os.pathsep.join([temp, root])
            result = subprocess.run([sys.executable, '-c', 'from audiopod.engine import PiperEngine; PiperEngine("unused", {})'], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('opt-out reached before inference', result.stderr)
            self.assertNotIn('native runtime imported before telemetry opt-out', result.stderr)


if __name__ == '__main__':
    unittest.main()
