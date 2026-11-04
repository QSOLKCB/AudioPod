"""Small reproducible preparation benchmark; does not measure speech inference."""
import statistics
import time

from audiopod.books import split_text


def measure(splitter=split_text):
    rows = []
    for size in (500_000, 2_000_000, 8_000_000):
        source = ('A clear sentence preserves every word. ' * (size // 38 + 1))[:size]
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            chunks = list(splitter(source))
            samples.append(time.perf_counter() - start)
        assert ' '.join(chunks).split() == source.split(), 'Text was lost, repeated or split mid-word'
        row = {'characters': len(source), 'chunks': len(chunks), 'median_seconds': round(statistics.median(samples), 6)}
        rows.append(row)
        print(row)
    return rows


if __name__ == '__main__':
    measure()
