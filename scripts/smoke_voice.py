"""Explicit integration test using an already-installed voice; no downloads here."""
import argparse
import json
from pathlib import Path
import socket
import tempfile
import wave
from unittest.mock import patch

from audiopod.books import load_book
from audiopod.audio import measure_wav
from audiopod.render import render_book
from audiopod.voices import default_model

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path)
args = parser.parse_args()
with tempfile.TemporaryDirectory() as temp:
    output = args.output or Path(temp) / 'audio'
    source = Path(__file__).resolve().parents[1] / 'examples/first-listen.md'
    # Fail this test if narration tries to create any network socket.
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Narration attempted network access')), patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('Narration attempted network access')):
        render_book(load_book(source), default_model(), output)
        render_book(load_book(source), default_model(), output, resume=True)
    for path in sorted(output.glob('*.wav')):
        with wave.open(str(path)) as wav:
            assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
            assert wav.getnframes() > wav.getframerate()
            audio = wav.readframes(wav.getnframes())
            assert any(audio), 'Voice produced silence'
            print(f'{path.name}: {wav.getnframes() / wav.getframerate():.2f}s, {wav.getframerate()} Hz')
    receipt = json.loads((output / 'audiopod.json').read_text())
    assert len(receipt['completed']) == 2
    for record in receipt['completed'].values():
        quality = record['pcm_quality']
        measured = measure_wav(output / record['file'], quality['sample_rate'], quality['frames'])
        assert all(quality[field] == value for field, value in measured.items())
        assert quality['frames'] == quality['source_frames'] + quality['pause_frames_added']
        assert quality['sample_peak_dbfs'] <= -.999 and quality['clipped_samples'] == 0
        print(f"{record['file']}: {quality['phrases']} phrases, {quality['sample_peak_dbfs']:.2f} dBFS peak, {quality['rms_dbfs']:.2f} dBFS RMS")
    print('Offline voice synthesis and verified resume passed.')
