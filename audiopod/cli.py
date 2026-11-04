"""Shared CLI and desktop entry point."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import signal
import sys
import threading

from . import AudioPodError, Cancelled, __version__
from .books import load_book
from .render import Settings, render_book
from .voices import default_model, install_voice


def chapter_selection(value, count):
    if not value:
        return None
    chosen = set()
    try:
        for part in value.split(","):
            endpoints = part.strip().split("-")
            if len(endpoints) > 2:
                raise ValueError
            first, last = int(endpoints[0]), int(endpoints[-1])
            if not 1 <= first <= last <= count:
                raise ValueError
            chosen.update(range(first - 1, last))
    except ValueError as exc:
        raise AudioPodError(f"Chapter selection must be numbers or ranges within 1–{count}, for example 1,3-5.") from exc
    return sorted(chosen)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Turn local text and EPUB books into offline audiobooks.")
    parser.add_argument("--version", action="version", version=f"AudioPod {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="Open the desktop app (also the default)")
    commands.add_parser("install-voice", help="Download and verify Cori (about 61 MiB); only this command accesses the network")
    inspect = commands.add_parser("inspect", help="List a book's imported reading order without loading a voice")
    inspect.add_argument("source", type=Path)
    inspect.add_argument("--json", action="store_true")
    render = commands.add_parser("render", help="Narrate a book using an installed local voice")
    render.add_argument("source", type=Path)
    render.add_argument("--output", type=Path, required=True, help="New/empty folder, or a matching job with --resume")
    render.add_argument("--model", type=Path, default=default_model())
    render.add_argument("--format", choices=["wav", "mp3", "m4b"], default="wav")
    render.add_argument("--speed", type=float, default=1.0)
    render.add_argument("--speaker", type=int, default=0)
    render.add_argument("--threads", type=int, default=4)
    render.add_argument("--chapters", help="Section numbers from inspect, for example 2,4-7")
    render.add_argument("--title")
    render.add_argument("--author")
    render.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    cancelled = threading.Event()
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, lambda signum, frame: cancelled.set())
    try:
        if args.command in {None, "gui"}:
            try:
                from .gui import launch
                return launch()
            except ImportError as exc:
                raise AudioPodError("Tk is not installed in this Python. See README desktop setup, or use the CLI.") from exc
        if args.command == "install-voice":
            install_voice(print, cancelled.is_set)
            return 0
        book = load_book(args.source)
        if args.command == "inspect":
            data = {"title": book.title, "author": book.author, "language": book.language,
                    "source_sha256": book.source_sha256, "words": book.words,
                    "sections": [{"number": i + 1, "title": c.title, "words": len(c.text.split())} for i, c in enumerate(book.chapters)]}
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print(f"{book.title} — {book.author}\n{book.words:,} words · {len(book.chapters)} sections")
                for chapter in data["sections"]:
                    print(f"{chapter['number']:>3}. {chapter['title']} ({chapter['words']:,} words)")
            return 0
        if args.title is not None:
            book = replace(book, title=args.title)
        if args.author is not None:
            book = replace(book, author=args.author)
        render_book(book, args.model, args.output, Settings(args.speed, args.speaker, args.threads, args.format),
                    chapter_selection(args.chapters, len(book.chapters)), args.resume,
                    lambda e: print(f"{e['fraction']:.0%} · {e['message']}", flush=True), cancelled.is_set)
        return 0
    except Cancelled as exc:
        print(str(exc), file=sys.stderr)
        return 130
    except (AudioPodError, OSError) as exc:
        print(f"AudioPod: {exc}", file=sys.stderr)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
