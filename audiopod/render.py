"""Atomic chapter exports with verified resume receipts."""

from dataclasses import asdict, dataclass, replace
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import wave

from . import AudioPodError, Cancelled, __version__
from .engine import PiperEngine
from .player import player_html
from .voices import inspect_model, sha256_file


@dataclass(frozen=True)
class Settings:
    speed: float = 1.0
    speaker: int = 0
    threads: int = 4
    format: str = "wav"

    def validate(self):
        if type(self.speed) not in (float, int) or not 0.5 <= self.speed <= 2.0:
            raise AudioPodError("Narration speed must be between 0.5 and 2.0.")
        if type(self.threads) is not int or not 1 <= self.threads <= 32:
            raise AudioPodError("CPU threads must be between 1 and 32.")
        if self.format not in {"wav", "mp3", "m4b"}:
            raise AudioPodError("Choose WAV, MP3, or M4B output.")
        if type(self.speaker) is not int or self.speaker < 0:
            raise AudioPodError("Speaker ID must be a nonnegative integer.")


def read_manifest(folder):
    path = Path(folder) / "audiopod.json"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST:
            raise AudioPodError("Choose an AudioPod output folder with a regular audiopod.json manifest.")
        with path.open(encoding="utf-8") as f:
            content = f.read(MAX_MANIFEST + 1)
        if len(content) > MAX_MANIFEST:
            raise AudioPodError("Resume manifest is too large.")
        receipt = json.loads(content)
        if not isinstance(receipt, dict) or receipt.get("schema") != 1 or not isinstance(receipt.get("identity"), dict):
            raise AudioPodError("Invalid or unsupported resume manifest.")
        return receipt
    except (OSError, ValueError, RecursionError) as exc:
        raise AudioPodError(f"Could not read resume settings: {exc}") from exc


def resume_options(book, folder):
    """Restore saved options; render_book still validates every byte before writing."""
    identity = read_manifest(folder)["identity"]
    try:
        if identity.get("source_sha256") != book.source_sha256:
            raise AudioPodError("Open the original source book before resuming this folder.")
        settings = Settings(**identity["settings"])
        settings.validate()
        for field in ("title", "author", "language"):
            if not isinstance(identity[field], str):
                raise AudioPodError("Invalid book metadata in resume settings.")
        selected = [c["index"] for c in identity["chapters"]]
        if not selected or any(type(i) is not int or not 0 <= i < len(book.chapters) for i in selected) or selected != sorted(set(selected)):
            raise AudioPodError("Invalid section selection in resume settings.")
        return replace(book, title=identity["title"], author=identity["author"], language=identity["language"]), settings, selected
    except (TypeError, ValueError, KeyError) as exc:
        raise AudioPodError(f"Invalid resume settings: {exc}") from exc


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _runtime_versions():
    versions = {}
    for package in ("piper-tts", "onnxruntime", "numpy"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not installed"
    return versions


def _atomic(path, content):
    if path.is_symlink():
        raise AudioPodError(f"Refusing to replace a linked file: {path.name}")
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def _ffmpeg(args, cancelled):
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AudioPodError("FFmpeg is required for MP3/M4B. Install it or choose WAV.")
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen([exe, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-n", *args], stdout=subprocess.DEVNULL, stderr=log)
        try:
            while proc.poll() is None:
                if cancelled():
                    raise Cancelled("Encoding cancelled. Completed chapters remain available.")
                time.sleep(0.1)
            if proc.returncode:
                log.seek(0)
                message = log.read(8192).decode("utf-8", errors="replace").strip()
                raise AudioPodError(f"FFmpeg failed: {message or proc.returncode}")
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def _meta(value):
    return str(value).replace("\\", "\\\\").replace("\n", " ").replace("\r", " ").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")


def _m4b(folder, book, records, cancelled):
    # Controlled numeric file names keep FFmpeg's concat demuxer in safe mode.
    with tempfile.TemporaryDirectory(prefix=".encode-", dir=folder) as temp:
        temp = Path(temp)
        concat = folder / ".concat.txt"
        metadata = temp / "chapters.txt"
        target = temp / "book.m4b"
        _atomic(concat, "ffconcat version 1.0\n" + "".join(f"file '{r['file']}'\n" for r in records))
        lines = [";FFMETADATA1", f"title={_meta(book.title)}", f"artist={_meta(book.author)}"]
        elapsed = 0
        for record in records:
            end = elapsed + round(record["duration"] * 1000)
            lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={elapsed}", f"END={end}", f"title={_meta(record['title'])}"]
            elapsed = end
        metadata.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            _ffmpeg(["-f", "concat", "-safe", "1", "-i", str(concat), "-i", str(metadata), "-map", "0:a:0", "-map_metadata", "1", "-map_chapters", "1", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(target)], cancelled)
            os.replace(target, folder / "book.m4b")
        finally:
            concat.unlink(missing_ok=True)


def render_book(book, model, output, settings=Settings(), selected=None, resume=False,
                progress=lambda event: None, cancelled=lambda: False, engine_factory=PiperEngine):
    settings.validate()
    selected = list(range(len(book.chapters))) if selected is None else sorted(set(selected))
    if not selected or any(not isinstance(i, int) or i < 0 or i >= len(book.chapters) for i in selected):
        raise AudioPodError("Select at least one existing chapter.")
    config, voice_hashes = inspect_model(model)
    if not 0 <= settings.speaker < config["num_speakers"]:
        raise AudioPodError("Speaker number is not present in this voice.")
    if settings.format != "wav" and not shutil.which("ffmpeg"):
        raise AudioPodError("FFmpeg is required for MP3/M4B. Install it or choose WAV.")
    identity = {"app": __version__, "runtime": _runtime_versions(), "source_sha256": book.source_sha256,
                "title": book.title, "author": book.author, "language": book.language,
                "chapters": [{"index": i, "title": book.chapters[i].title, "text_sha256": hashlib.sha256(book.chapters[i].text.encode()).hexdigest()} for i in selected],
                "voice": voice_hashes, "settings": asdict(settings)}
    key = hashlib.sha256(_canonical(identity).encode()).hexdigest()
    folder = Path(output).absolute()
    if resume and not folder.is_dir():
        raise AudioPodError("Resume folder does not exist. Choose the original output folder.")
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink():
        raise AudioPodError("Choose an ordinary output directory, not a symbolic link.")
    lock = folder / ".audiopod-lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise AudioPodError("This output folder is locked by another job. See README for recovery after a forced stop.") from exc
    player_dirty = False
    save_player = None
    try:
        manifest_path = folder / "audiopod.json"
        entries = [p for p in folder.iterdir() if p != lock]
        if resume:
            receipt = read_manifest(folder)
            if receipt.get("identity") != identity or receipt.get("key") != key:
                raise AudioPodError("This folder belongs to different text, chapters, voice, or settings. Choose a new output folder.")
        else:
            if entries:
                raise AudioPodError("Output folder is not empty. Choose a new folder, or enable resume for the same job.")
            receipt = {"schema": 1, "key": key, "identity": identity, "completed": {}}
        if not isinstance(receipt.get("completed"), dict):
            raise AudioPodError("Invalid chapter records in resume manifest.")
        records, engine = [], None
        extension = "mp3" if settings.format == "mp3" else "wav"
        # Validate the ENTIRE saved job before creating audio or rewriting its player.
        if set(receipt["completed"]) - {str(i) for i in selected}:
            raise AudioPodError("Resume manifest contains unselected chapter records.")
        for index in selected:
            if cancelled():
                raise Cancelled("Verification cancelled; existing files were left intact.")
            name = f"{index + 1:04d}.{extension}"
            target = folder / name
            if target.is_symlink():
                raise AudioPodError(f"Refusing linked audio file: {name}")
            if str(index) in receipt["completed"]:
                record = receipt["completed"][str(index)]
                if not isinstance(record, dict) or record.get("file") != name or record.get("index") != index or record.get("title") != book.chapters[index].title:
                    raise AudioPodError("Invalid chapter record in resume manifest.")
                duration = record.get("duration")
                if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
                    raise AudioPodError("Invalid chapter duration in resume manifest.")
                progress({"message": f"Checking saved audio: {record['title']}", "fraction": 0})
                if not target.is_file() or sha256_file(target) != record.get("sha256"):
                    raise AudioPodError(f"Saved audio {name} is missing or changed. Use a new output folder.")
                records.append(record)
            elif target.exists():
                raise AudioPodError(f"Untracked audio {name} already exists. Move it aside before resuming.")
        if settings.format == "m4b":
            target = folder / "book.m4b"
            if target.is_symlink():
                raise AudioPodError("Refusing a linked M4B file.")
            if receipt.get("m4b_sha256"):
                if len(records) != len(selected) or not target.is_file() or sha256_file(target) != receipt["m4b_sha256"]:
                    raise AudioPodError("Saved M4B is missing or changed, or its chapter records are incomplete. Use a new output folder.")
            elif target.exists():
                raise AudioPodError("Untracked book.m4b exists. Move it aside before resuming.")

        last_player_write = 0.0
        player_dirty = False
        def save_player():
            nonlocal last_player_write, player_dirty
            tracks = [{**r, "text": book.chapters[r["index"]].text} for r in sorted(records, key=lambda r: r["index"])]
            _atomic(folder / "listen.html", player_html(book.title, book.author, tracks, key, book.language))
            _atomic(folder / "playlist.m3u", "#EXTM3U\n" + "".join(r["file"] + "\n" for r in tracks))
            last_player_write = time.monotonic()
            player_dirty = False

        def save():
            nonlocal player_dirty
            _atomic(manifest_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
            player_dirty = True
            if time.monotonic() - last_player_write >= 2.0:
                save_player()

        # Keep the previous listening page intact until resume validation succeeds.
        if not resume:
            save()
        for number, index in enumerate(selected):
            if cancelled():
                raise Cancelled("Stopped. Completed chapters are saved.")
            chapter = book.chapters[index]
            name = f"{index + 1:04d}.{extension}"
            target = folder / name
            record = receipt["completed"].get(str(index))
            if record:
                progress({"message": f"Verified: {chapter.title}", "fraction": (number + 1) / len(selected)})
                continue
            if target.exists():
                raise AudioPodError(f"Untracked audio {name} already exists. Move it aside before resuming.")
            if engine is None:
                progress({"message": "Loading local voice…", "fraction": number / len(selected)})
                engine = engine_factory(model, config, settings.speed, settings.speaker, settings.threads)
            with tempfile.TemporaryDirectory(prefix=".chapter-", dir=folder) as temp:
                wav_path = Path(temp) / "audio.wav"
                engine.render(chapter.text, wav_path,
                              lambda done, total: progress({"message": f"{chapter.title} · chunk {done}/{total}", "fraction": (number + done / total) / len(selected)}), cancelled)
                with wave.open(str(wav_path), "rb") as wav:
                    duration = wav.getnframes() / wav.getframerate()
                produced = wav_path
                if settings.format == "mp3":
                    produced = Path(temp) / "audio.mp3"
                    _ffmpeg(["-i", str(wav_path), "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "96k", "-metadata", f"title={chapter.title}", "-metadata", f"album={book.title}", "-metadata", f"artist={book.author}", str(produced)], cancelled)
                record = {"index": index, "title": chapter.title, "file": name, "duration": duration, "sha256": sha256_file(produced)}
                os.replace(produced, target)
            receipt["completed"][str(index)] = record
            records.append(record)
            save()
        save()
        save_player()
        if settings.format == "m4b":
            target = folder / "book.m4b"
            if target.is_symlink():
                raise AudioPodError("Refusing a linked M4B file.")
            existing = receipt.get("m4b_sha256")
            if existing:
                if not target.is_file() or sha256_file(target) != existing:
                    raise AudioPodError("Saved M4B is missing or changed. Use a new output folder.")
            else:
                if target.exists():
                    raise AudioPodError("Untracked book.m4b exists. Move it aside before resuming.")
                progress({"message": "Encoding audiobook with chapter markers…", "fraction": 1})
                _m4b(folder, book, sorted(records, key=lambda r: r["index"]), cancelled)
                receipt["m4b_sha256"] = sha256_file(target)
                save()
        progress({"message": f"Ready to listen: {folder / 'listen.html'}", "fraction": 1})
        return folder / "listen.html"
    except (AudioPodError, KeyboardInterrupt):
        raise
    except (OSError, ValueError, KeyError, TypeError, OverflowError, wave.Error, EOFError, RuntimeError) as exc:
        raise AudioPodError(f"Could not finish the audiobook: {exc}") from exc
    finally:
        try:
            if player_dirty and save_player is not None:
                save_player()
        finally:
            lock.rmdir()


MAX_MANIFEST = 20 * 1024 * 1024
