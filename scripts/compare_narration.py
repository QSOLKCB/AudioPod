"""Render only the repository's public sample for an honest local A/B listen.

No downloads, MOS predictor or claim of perceptual optimality. Timings include
voice verification/loading and export; stochastic inference differs per run.
"""
import argparse
import json
import math
from pathlib import Path
import socket
import time
from unittest.mock import patch
import wave

from audiopod.audio import BLOCK_FRAMES
from audiopod.books import load_book
from audiopod.prosody import NATURAL, ORIGINAL
from audiopod.render import Settings, render_book
from audiopod.voices import default_model


def measure(path):
    import numpy as np
    count, peak, squares, full_scale = 0, 0, 0., 0
    with wave.open(str(path), 'rb') as wav:
        rate = wav.getframerate()
        assert (wav.getnchannels(), wav.getsampwidth()) == (1, 2)
        while raw := wav.readframes(BLOCK_FRAMES):
            samples = np.frombuffer(raw, dtype='<i2').astype(np.float64)
            count += len(samples)
            peak = max(peak, int(np.max(np.abs(samples))))
            squares += float(np.dot(samples, samples))
            full_scale += int(np.count_nonzero(np.abs(samples) >= 32767))
    assert peak > 0 and count > 0
    return {'duration_seconds': count / rate, 'frames': count, 'sample_rate': rate,
            'sample_peak_dbfs': 20 * math.log10(peak / 32767),
            'rms_dbfs': 10 * math.log10(squares / count / (32767 ** 2)),
            'full_scale_samples': full_scale}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New/empty folder for both WAVs, players and comparison.json')
    parser.add_argument('--model', type=Path, default=default_model())
    args = parser.parse_args()
    if args.output.is_symlink() or (args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir()))):
        parser.error('Choose a new or empty output folder.')
    args.output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / 'examples/voice-check.md'
    book = load_book(source)
    results = {}
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Narration attempted network access')), patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('Narration attempted network access')):
        for name, profile in (('original', ORIGINAL), ('natural', NATURAL)):
            folder = args.output / name
            started = time.perf_counter()
            render_book(book, args.model, folder, settings=Settings(profile=profile))
            elapsed = time.perf_counter() - started
            receipt = json.loads((folder / 'audiopod.json').read_text(encoding='utf-8'))
            record = receipt['completed']['0']
            measured = measure(folder / record['file'])
            if profile == NATURAL:
                assert measured['sample_peak_dbfs'] <= -.999 and measured['full_scale_samples'] == 0
                assert measured['frames'] == record['pcm_quality']['source_frames'] + record['pcm_quality']['pause_frames_added']
            results[name] = {'render_seconds': elapsed, 'identity': receipt['identity'], 'audio_sha256': record['sha256'],
                             'measurement': measured, 'pcm_quality': record.get('pcm_quality')}
            print(f"{name}: {measured['duration_seconds']:.2f}s audio, {elapsed:.2f}s render, "
                  f"{measured['sample_peak_dbfs']:.2f} dBFS sample peak, {measured['rms_dbfs']:.2f} dBFS RMS")
    report = {'sample': 'examples/voice-check.md', 'limits': 'Signal measurements, not a perceptual quality score. Inference is stochastic; compare at a comfortable listening volume.',
              'results': results}
    (args.output / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print('Open each folder’s listen.html to compare the public sample. No human listening score is implied.')


if __name__ == '__main__':
    main()
