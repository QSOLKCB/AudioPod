"""Small local preferences: paths/settings only, never book text."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .voices import data_home, default_model


def defaults():
    return {"model": str(default_model()), "output_parent": str(Path.home() / "AudioPod"),
            "speed": 1.0, "speaker": 0, "threads": 4, "format": "mp3" if shutil.which("ffmpeg") else "wav", "font_size": 11}


def validated(values):
    clean = defaults()
    if not isinstance(values, dict):
        return clean
    for key in ("model", "output_parent"):
        value = values.get(key)
        if isinstance(value, str) and 0 < len(value) < 4096 and "\x00" not in value:
            clean[key] = value
    for key, low, high in (("speaker", 0, 999), ("threads", 1, 32), ("font_size", 10, 24)):
        value = values.get(key)
        if type(value) is int and low <= value <= high:
            clean[key] = value
    speed = values.get("speed")
    if type(speed) in (int, float) and 0.5 <= speed <= 2:
        clean["speed"] = speed
    if values.get("format") in ("wav", "mp3", "m4b"):
        clean["format"] = values["format"]
    return clean


def load_preferences():
    try:
        path = data_home() / "preferences.json"
        if not path.is_file() or path.stat().st_size > 16384:
            return defaults()
        return validated(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError):
        return defaults()


def save_preferences(values):
    temp = None
    try:
        folder = data_home()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "preferences.json"
        if path.is_symlink():
            return False
        fd, temp = tempfile.mkstemp(prefix=".preferences-", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(validated(values), f, ensure_ascii=False, indent=2)
        os.replace(temp, path)
        return True
    except (OSError, ValueError):
        return False
    finally:
        if temp:
            Path(temp).unlink(missing_ok=True)


def suggested_output(parent, title):
    # Prefix avoids Windows reserved device basenames; no source path characters.
    slug = re.sub(r"[^\w-]+", "-", title, flags=re.UNICODE).strip("-_")[:60] or "book"
    base = Path(parent).expanduser() / ("audiopod-" + slug)
    candidate, suffix = base, 2
    while candidate.exists() or candidate.is_symlink():
        candidate = base.with_name(f"{base.name}-{suffix}")
        suffix += 1
    return candidate
