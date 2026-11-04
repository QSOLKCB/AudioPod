"""Bounded, offline import. EPUB spine order is the reading order."""

from dataclasses import dataclass, replace
from functools import cached_property
import hashlib
from html import unescape
import posixpath
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from . import AudioPodError

MAX_TEXT = 20 * 1024 * 1024
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_ENTRY = 16 * 1024 * 1024


@dataclass(frozen=True)
class Chapter:
    title: str
    text: str

    @cached_property
    def words(self):
        return len(self.text.split())


@dataclass(frozen=True)
class Book:
    title: str
    author: str
    language: str
    chapters: tuple[Chapter, ...]
    source_sha256: str

    @cached_property
    def words(self):
        return sum(c.words for c in self.chapters)


def _clean(text):
    return "\n\n".join(" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip())


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _xml(data):
    # ElementTree does not fetch external resources; disallow entity declarations too.
    declaration_text = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    if re.search(r"<!\s*ENTITY\b", declaration_text, re.I):
        raise AudioPodError("EPUB XML entity declarations are not supported.")
    return ET.fromstring(data)


def _member(parent, href):
    url = urlsplit(href)
    if url.scheme or url.netloc or url.query or "\\" in href:
        raise AudioPodError("EPUB references a non-local resource.")
    path = unquote(url.path)
    if not path or path.startswith("/") or "\x00" in path:
        raise AudioPodError("Invalid EPUB resource path.")
    path = posixpath.normpath(posixpath.join(posixpath.dirname(parent), path))
    if path == ".." or path.startswith("../"):
        raise AudioPodError("EPUB resource escapes the archive.")
    return path


def _xhtml(data):
    root = _xml(data)
    body = next((e for e in root.iter() if _local(e.tag) == "body"), root)
    chunks, headings = [], []
    blocks = {"p", "div", "section", "article", "blockquote", "li", "pre", "br", "hr", "tr", "td", "th", "dt", "dd", "figcaption"}

    def walk(e):
        tag = _local(e.tag)
        if tag in {"head", "script", "style", "nav"} or "hidden" in e.attrib or e.get("aria-hidden") == "true":
            return
        heading = tag in {"h1", "h2", "h3", "h4", "h5", "h6"}
        start = len(chunks)
        if heading or tag in blocks:
            chunks.append("\n\n")
        if tag == "img" and e.get("alt"):
            chunks.append(e.get("alt"))
        if e.text:
            chunks.append(e.text)
        for child in e:
            walk(child)
            if child.tail:
                chunks.append(child.tail)
        if heading or tag in blocks:
            chunks.append("\n\n")
        if heading:
            headings.append(" ".join("".join(chunks[start:]).split()))

    walk(body)
    return _clean("".join(chunks)), next((h for h in headings if h), "")


def _epub(path):
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        names = [i.filename for i in entries]
        if len(entries) > 10000 or len(names) != len(set(names)):
            raise AudioPodError("EPUB has too many or duplicate archive entries.")
        if sum(i.file_size for i in entries) > 512 * 1024 * 1024:
            raise AudioPodError("EPUB expands beyond the 512 MiB import limit.")
        if any(i.flag_bits & 1 for i in entries) or "META-INF/encryption.xml" in names:
            raise AudioPodError("Encrypted EPUB resources are not supported. Use a DRM-free text or EPUB export.")

        def read(name):
            info = z.getinfo(name)
            if info.file_size > MAX_ENTRY:
                raise AudioPodError("An EPUB text entry exceeds 16 MiB.")
            with z.open(info) as f:
                data = f.read(MAX_ENTRY + 1)
            if len(data) > MAX_ENTRY:
                raise AudioPodError("An EPUB text entry exceeds 16 MiB.")
            return data

        container = _xml(read("META-INF/container.xml"))
        rootfile = next((e for e in container.iter() if _local(e.tag) == "rootfile"), None)
        if rootfile is None:
            raise AudioPodError("EPUB has no package document.")
        opf_path = _member("", rootfile.get("full-path", ""))
        opf = _xml(read(opf_path))
        meta = next((e for e in opf if _local(e.tag) == "metadata"), None)

        def metadata(key, fallback=""):
            if meta is None:
                return fallback
            return next(("".join(e.itertext()).strip() for e in meta if _local(e.tag) == key), fallback)

        manifest = {e.get("id"): e for e in opf.iter() if _local(e.tag) == "item"}
        chapters = []
        total = 0
        for ref in (e for e in opf.iter() if _local(e.tag) == "itemref"):
            if ref.get("linear", "yes") == "no":
                continue
            item = manifest.get(ref.get("idref"))
            if item is None:
                raise AudioPodError("EPUB spine references a missing item.")
            if "nav" in item.get("properties", "").split():
                continue
            if item.get("media-type") not in {"application/xhtml+xml", "text/html"}:
                raise AudioPodError("EPUB contains an unsupported reading-order item.")
            text, title = _xhtml(read(_member(opf_path, item.get("href", ""))))
            # Image-only cover pages have no prose; descriptive image alt remains readable.
            if not text:
                continue
            total += len(text.encode("utf-8"))
            if total > MAX_TEXT:
                raise AudioPodError("Book text exceeds the 20 MiB import limit.")
            chapters.append(Chapter(title or f"Section {len(chapters) + 1}", text))
        return Book(metadata("title", path.stem), metadata("creator"), metadata("language", "en"), tuple(chapters), "")


def _inline_markdown(text):
    # Keep visible link labels and image descriptions; never fetch their destinations.
    text = re.sub(r"!?\[([^\]]*)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*```[^\n]*$", "", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|>\s?|[-*+]\s+)", "", text)
    text = re.sub(r"(`+|\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<!\w)(\*|_)(?=\S)(.+?)\1(?!\w)", r"\2", text)
    return unescape(text)


def _text_book(path, raw):
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        raise AudioPodError("Text contains NUL bytes. Export the document as UTF-8 text.")
    markdown = path.suffix.lower() in {".md", ".markdown"}
    meta = {}
    if markdown and text.startswith("---\n"):
        front = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
        if front:
            for line in front[1].splitlines():
                key, sep, value = line.partition(":")
                if sep and key in {"title", "author", "lang"}:
                    meta[key] = value.strip().strip("\"'")
            text = text[front.end():]
    chapters, lines, title = [], [], "Opening"

    def finish():
        content = "\n".join(lines)
        if markdown:
            content = _inline_markdown(content)
        content = _clean(content)
        if content:
            chapters.append(Chapter(title, content))

    for line in text.splitlines():
        heading = re.match(r"^#{1,2}\s+(.+?)\s*#*\s*$", line) if markdown else re.match(
            r"^((?:chapter|part)\s+[\wIVXLCDM]+(?:\s.*|[.:—–-].*)?|prologue|epilogue|copyright|also by .+)\s*$", line, re.I)
        if heading:
            finish()
            title, lines = heading[1], [heading[1]]
        else:
            lines.append(line)
    finish()
    return Book(meta.get("title", path.stem), meta.get("author", ""), meta.get("lang", "en"), tuple(chapters), "")


def load_book(filename):
    path = Path(filename)
    try:
        if not path.is_file():
            raise AudioPodError("Choose a regular book file; directories, pipes and devices are not supported.")
        limit = MAX_ARCHIVE if path.suffix.lower() == ".epub" else MAX_TEXT
        with path.open("rb") as f:
            raw = f.read(limit + 1)
        if len(raw) > limit:
            raise AudioPodError(f"Input exceeds the {limit // 1024 // 1024} MiB limit.")
        if path.suffix.lower() == ".epub":
            # Parse the same snapshot that is hashed, even if the source changes.
            import io
            snapshot = io.BytesIO(raw)
            snapshot.stem = path.stem
            book = _epub(snapshot)
        elif path.suffix.lower() in {".txt", ".md", ".markdown"}:
            book = _text_book(path, raw)
        else:
            raise AudioPodError("Choose a DRM-free EPUB, UTF-8 TXT, or Markdown file.")
        if not book.chapters:
            raise AudioPodError("No readable text was found.")
        return replace(book, source_sha256=hashlib.sha256(raw).hexdigest())
    except AudioPodError:
        raise
    except (OSError, ValueError, KeyError, UnicodeError, ET.ParseError, zipfile.BadZipFile, RuntimeError) as exc:
        raise AudioPodError(f"Could not import {path.name}: {exc}") from exc


def split_text(text, limit=600):
    """Bound memory at word/sentence boundaries without deleting or repeating text."""
    if limit < 32:
        raise ValueError("Chunk limit must be at least 32 characters.")
    start, size = 0, len(text)
    while start < size:
        while start < size and text[start].isspace():
            start += 1
        if size - start <= limit:
            tail = text[start:].strip()
            if tail:
                yield tail
            return
        window = text[start:start + limit]
        boundaries = list(re.finditer(r"[.!?。！？][\"'’”]?\s+|\n\s*\n", window))
        end = boundaries[-1].end() if boundaries else 0
        if end < limit // 3:
            # A short opening sentence must not force a cut through a later word.
            end = next((i for i in range(len(window) - 1, -1, -1) if window[i].isspace()), 0)
        if not end:
            end = limit  # Unbroken tokens/scripts still need a bounded chunk.
        chunk = text[start:start + end].strip()
        start += end
        if chunk:
            yield chunk
