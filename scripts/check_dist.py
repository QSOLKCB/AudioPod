"""Keep runtime environments, caches, voices and user media out of distributions."""
from pathlib import Path, PurePosixPath
import tarfile
import zipfile

archives = sorted(Path('dist').glob('audiopod-*'))
assert any(p.suffix == '.whl' for p in archives)
assert any(p.name.endswith('.tar.gz') for p in archives)
for path in archives:
    assert path.stat().st_size < 1024 * 1024, f'Unexpectedly large app archive: {path.name}'
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    else:
        with tarfile.open(path) as t:
            entries = t.getmembers()
            assert not any(e.issym() or e.islnk() for e in entries), 'Source archive contains links'
            names = [e.name for e in entries]
        for guide in ('INSTALLATION.md', 'GETTING_STARTED.md', 'TROUBLESHOOTING.md'):
            assert any(n.endswith('docs/' + guide) for n in names), f'Missing guide: {guide}'
    for name in names:
        parts = PurePosixPath(name).parts
        assert not set(parts) & {'.venv', '.uv-cache', '.audiopod', '__pycache__'}, name
        assert not name.endswith(('.onnx', '.epub', '.wav', '.mp3', '.m4b')), name
    assert any(n.endswith('audiopod/cli.py') for n in names)
    print(f'{path.name}: {len(names)} entries, no environments, caches, voice weights or user media')
