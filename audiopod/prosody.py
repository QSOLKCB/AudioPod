"""Bounded, source-preserving phrase planning for the natural speech pipeline."""

from dataclasses import dataclass
import re

NATURAL = "natural-v1"
ORIGINAL = "original-v1"
PROFILE_LABELS = {"Natural": NATURAL, "Original": ORIGINAL}
PAUSE_SECONDS = {"sentence": .28, "paragraph": .50, "clause": .14,
                 "continuation": 0., "end": .18}
# Conservative English titles/abbreviations, not a general language parser.
ABBREVIATIONS = frozenset("mr mrs ms dr prof sr jr st mt rev fr gen col sgt capt lt vs e.g i.e".split())
STOPS = re.compile(r'''[.!?…。！？]["'’”\)\]]*''')
CLAUSES = re.compile(r'''[;:,—–]["'’”\)\]]*(?=\s)''')


@dataclass(frozen=True)
class Phrase:
    text: str
    boundary: str


def _paragraphs(text):
    start = 0
    for match in re.finditer(r"\n[ \t\r]*\n", text):
        yield start, match.start()
        start = match.end()
    yield start, len(text)


def phrases(text, limit=600):
    """Keep sentence/paragraph boundaries and every non-whitespace character.

    Long sentences prefer clauses, then whitespace, then a hard bound for an
    unbroken token. Only bounded windows are copied, even for very long chapters.
    """
    if type(limit) is not int or limit < 32:
        raise ValueError("Phrase limit must be an integer of at least 32 characters.")
    content_end = len(text)
    while content_end and text[content_end - 1].isspace():
        content_end -= 1
    for start, paragraph_end in _paragraphs(text):
        while paragraph_end > start and text[paragraph_end - 1].isspace():
            paragraph_end -= 1
        while start < paragraph_end:
            while start < paragraph_end and text[start].isspace():
                start += 1
            if start == paragraph_end:
                break
            window_end = min(start + limit, paragraph_end)
            window = text[start:window_end]
            cut, boundary = None, "sentence"
            for stop in STOPS.finditer(window):
                absolute_end = start + stop.end()
                mark = stop.group()[0]
                if absolute_end < paragraph_end and not text[absolute_end].isspace() and mark not in "。！？":
                    continue  # Decimals, domains, ellipsis interiors, etc.
                token = window[:stop.start() + 1].split()[-1].lower().strip('"\'“‘([{')
                if mark == "." and (token.rstrip(".") in ABBREVIATIONS or re.fullmatch(r"(?:[a-z]\.){2,}", token)):
                    continue
                next_word = text[absolute_end:min(paragraph_end, absolute_end + 40)].lstrip()
                if mark in "?!" and any(q in stop.group()[1:] for q in '\"”’') and next_word[:1].islower():
                    continue  # Keep quoted speech and its attribution together.
                cut = absolute_end
                break
            if cut is None:
                if window_end == paragraph_end:
                    cut = paragraph_end
                else:
                    clauses = [m.end() for m in CLAUSES.finditer(window) if m.end() >= limit // 3]
                    if clauses:
                        cut, boundary = start + clauses[-1], "clause"
                    else:
                        whitespace = next((i for i in range(len(window) - 1, -1, -1) if window[i].isspace()), 0)
                        cut, boundary = start + (whitespace or len(window)), "continuation"
            if cut == paragraph_end:
                boundary = "end" if paragraph_end == content_end else "paragraph"
            yield Phrase(text[start:cut].strip(), boundary)
            start = cut
