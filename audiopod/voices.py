"""Explicit voice installation. Narration never downloads resources."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

from . import AudioPodError, Cancelled

REVISION = "e7229f7d33a10e145e109b886d661984201ac3c4"
VOICE_ID = "en_GB-cori-medium"
BASE_URL = f"https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/en/en_GB/cori/medium"
FILES = {
    f"{VOICE_ID}.onnx": (63531379, "1899f98e5fb8310154f3c2973f4b8a929ba7245e722b3d3a85680b833d95f10d"),
    f"{VOICE_ID}.onnx.json": (4966, "e262c16d7f192f69d4edd6b4ef8a5915379e67495fcc402f1ab15eeb33da3d36"),
    "MODEL_CARD": (474, "38d76dfde845837b184668f8bab1c6426ad740b1af0fcebc349037822739e536"),
}


def data_home():
    if os.environ.get("AUDIOPOD_DATA_HOME"):
        return Path(os.environ["AUDIOPOD_DATA_HOME"]).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "AudioPod"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/AudioPod"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "audiopod"


def default_model():
    return data_home() / "voices" / VOICE_ID / f"{VOICE_ID}.onnx"


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def install_voice(progress=lambda message: None, cancelled=lambda: False):
    folder = default_model().parent
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for name, (size, digest) in FILES.items():
            target = folder / name
            if target.is_symlink():
                raise AudioPodError(f"Refusing to replace a linked voice file: {target}")
            if target.is_file() and target.stat().st_size == size and sha256_file(target) == digest:
                progress(f"Verified {name}")
                continue
            fd, tmp = tempfile.mkstemp(prefix=".download-", dir=folder)
            try:
                progress(f"Downloading {name} ({size / 1048576:.1f} MiB)")
                count, h = 0, hashlib.sha256()
                with os.fdopen(fd, "wb") as out, urllib.request.urlopen(f"{BASE_URL}/{name}", timeout=30) as response:
                    while True:
                        if cancelled():
                            raise Cancelled("Voice installation cancelled.")
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        count += len(block)
                        if count > size:
                            raise AudioPodError("Voice download exceeds its expected size.")
                        out.write(block)
                        h.update(block)
                if count != size or h.hexdigest() != digest:
                    raise AudioPodError("Voice download failed its SHA-256 check. Try installation again.")
                os.replace(tmp, target)
            finally:
                Path(tmp).unlink(missing_ok=True)
        progress("Cori voice is installed and verified.")
        return default_model()
    except (OSError, ValueError) as exc:
        raise AudioPodError(f"Could not install voice: {exc}") from exc


def inspect_model(model):
    model = Path(model)
    config_path = Path(str(model) + ".json")
    try:
        if not model.is_file() or not model.stat().st_size:
            raise AudioPodError("Voice is missing. Install Cori or choose a local Piper ONNX voice.")
        if not config_path.is_file():
            raise AudioPodError("Choose a voice with an adjacent regular .onnx.json file.")
        if config_path.stat().st_size > 1024 * 1024:
            raise AudioPodError("Voice configuration is too large.")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or not isinstance(config.get("audio"), dict):
            raise AudioPodError("Voice configuration must contain an audio settings object.")
        if config.get("phoneme_type", "espeak") != "espeak":
            raise AudioPodError("This version supports offline eSpeak-based Piper voices only.")
        rate = config["audio"]["sample_rate"]
        if not isinstance(rate, int) or not 8000 <= rate <= 96000:
            raise AudioPodError("Voice has an unsupported sample rate.")
        if not isinstance(config.get("num_speakers"), int) or config["num_speakers"] < 1:
            raise AudioPodError("Voice has an invalid speaker count.")
        hashes = {"model": sha256_file(model), "config": sha256_file(config_path)}
        if model.resolve() == default_model().resolve():
            if hashes["model"] != FILES[f"{VOICE_ID}.onnx"][1] or hashes["config"] != FILES[f"{VOICE_ID}.onnx.json"][1]:
                raise AudioPodError("Installed Cori voice failed verification. Reinstall the voice.")
        return config, hashes
    except AudioPodError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AudioPodError(f"Could not read the voice and its adjacent .onnx.json: {exc}") from exc
