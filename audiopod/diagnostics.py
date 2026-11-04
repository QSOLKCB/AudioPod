"""Offline setup checks; no package installation or native inference imports."""
from importlib.util import find_spec
from pathlib import Path
import shutil
import subprocess
import sys

from . import AudioPodError, __version__
from .render import _runtime_versions
from .voices import data_home, default_model, inspect_model


def diagnose(model=None):
    checks = []
    def add(name, ok, message, required=False):
        checks.append({"name": name, "ok": ok, "message": message, "required_for_wav": required})
    add("Python", (3, 11) <= sys.version_info[:2] < (3, 15), f"{sys.version.split()[0]} · {sys.executable}", True)
    versions = _runtime_versions()
    for package, module in (("piper-tts", "piper"), ("onnxruntime", "onnxruntime"), ("numpy", "numpy")):
        present = find_spec(module) is not None
        add(package, present, versions[package] if present else "Missing: run uv sync --locked in the AudioPod checkout.", True)
    add("Tk desktop module", find_spec("tkinter") is not None, "CLI works without Tk. To test an actual window: uv run --offline python -m tkinter")
    model = Path(model) if model else default_model()
    try:
        config, _ = inspect_model(model)
        add("Voice", True, f"{model} · {config['audio']['sample_rate']} Hz · {config['num_speakers']} speaker(s)", True)
    except AudioPodError as exc:
        add("Voice", False, str(exc), True)
    ffmpeg = shutil.which("ffmpeg")
    encoders = ""
    if ffmpeg:
        try:
            process = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10)
            if process.returncode == 0:
                encoders = process.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    for label, encoder in (("MP3 encoder", "libmp3lame"), ("M4B encoder", "aac")):
        available = any(len(line.split()) > 1 and line.split()[1] == encoder for line in encoders.splitlines())
        add(label, available, f"{ffmpeg} · {encoder}" if available else f"Install FFmpeg with {encoder}, or choose WAV.")
    return {"audiopod": __version__, "data_home": str(data_home()), "checks": checks,
            "ready_for_wav": all(c["ok"] for c in checks if c["required_for_wav"]),
            "note": "Checks are local. Module presence does not test voice inference or display access; use Voice preview next."}


def format_diagnostics(report):
    lines = [f"AudioPod {report['audiopod']} · setup check", f"Local data: {report['data_home']}", ""]
    lines.extend(f"{'OK' if c['ok'] else 'ACTION'} — {c['name']}: {c['message']}" for c in report["checks"])
    lines.extend(["", "WAV prerequisites found." if report["ready_for_wav"] else "Complete the required setup steps above.", report["note"]])
    return "\n".join(lines)
