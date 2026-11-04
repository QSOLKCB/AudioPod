import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from audiopod import AudioPodError
from audiopod.books import load_book, split_text
from audiopod.cli import chapter_selection


def epub(path, body='<h1>Chapter One</h1><p>Hello <em>there</em>, reader.</p>', href='chapter.xhtml', extra=None):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="EPUB/book.opf"/></rootfiles></container>')
        z.writestr('EPUB/book.opf', f'''<package><metadata><title>A Book</title><creator>An Author</creator><language>en</language></metadata><manifest>
<item id="two" href="two.xhtml" media-type="application/xhtml+xml"/>
<item id="one" href="{href}" media-type="application/xhtml+xml"/>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
</manifest><spine><itemref idref="nav"/><itemref idref="one"/><itemref idref="two"/></spine></package>''')
        z.writestr('EPUB/chapter.xhtml', f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{body}</body></html>')
        z.writestr('EPUB/two.xhtml', '<html><body><h1>Chapter Two</h1><p>Next.</p></body></html>')
        if extra:
            z.writestr(*extra)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_epub_reading_order_and_inline_spacing(self):
        path = self.root / 'book.epub'
        epub(path)
        book = load_book(path)
        self.assertEqual(book.title, 'A Book')
        self.assertEqual(book.author, 'An Author')
        self.assertEqual([c.title for c in book.chapters], ['Chapter One', 'Chapter Two'])
        self.assertEqual(book.chapters[0].text, 'Chapter One\n\nHello there, reader.')
        self.assertEqual(book.source_sha256, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_excludes_navigation_scripts_and_hidden_text(self):
        path = self.root / 'book.epub'
        epub(path, '<h1>One</h1><script>bad()</script><nav>Contents</nav><p hidden="hidden">Secret</p><p>Visible.</p>')
        self.assertEqual(load_book(path).chapters[0].text, 'One\n\nVisible.')

    def test_rejects_external_and_escaping_resources(self):
        for href in ['https://example.com/a.xhtml', '../../../a.xhtml', '/etc/passwd', '%2e%2e/%2e%2e/a.xhtml']:
            with self.subTest(href=href):
                path = self.root / 'book.epub'
                epub(path, href=href)
                with self.assertRaises(AudioPodError):
                    load_book(path)

    def test_encrypted_epub_error(self):
        path = self.root / 'book.epub'
        epub(path, extra=('META-INF/encryption.xml', '<encryption/>'))
        with self.assertRaisesRegex(AudioPodError, 'Encrypted'):
            load_book(path)

    def test_malformed_epub_is_actionable(self):
        for data in [b'not a zip', b'PK\x03\x04']:
            path = self.root / 'book.epub'
            path.write_bytes(data)
            with self.assertRaises(AudioPodError):
                load_book(path)

    def test_entities_rejected(self):
        path = self.root / 'book.epub'
        epub(path, '<!ENTITY text "bad">')
        with self.assertRaises(AudioPodError):
            load_book(path)

    def test_markdown_metadata_headings_and_visible_labels(self):
        book = load_book(self.write('book.md', '---\ntitle: My Book\nauthor: Writer\nlang: en-AU\n---\n# Part One\n\n## Chapter 1\n\n**Hello**, [reader](https://example.com).\n'))
        self.assertEqual((book.title, book.author, book.language), ('My Book', 'Writer', 'en-AU'))
        self.assertEqual([c.title for c in book.chapters], ['Part One', 'Chapter 1'])
        self.assertEqual(book.chapters[1].text, 'Chapter 1\n\nHello, reader.')

    def test_plain_text_preserves_punctuation_and_unicode(self):
        book = load_book(self.write('book.txt', '\ufeffChapter 1 — Water\n\n“Hello,” she said.\n\nChapter 2 — Sky\n\nEnki’s door.'))
        self.assertEqual(len(book.chapters), 2)
        self.assertIn('“Hello,” she said.', book.chapters[0].text)
        self.assertIn('Enki’s door.', book.chapters[1].text)

    def test_empty_binary_and_missing_inputs(self):
        for name, text in [('empty.txt', ' \n '), ('binary.txt', '\0data'), ('unsupported.pdf', 'Hello')]:
            with self.subTest(name=name), self.assertRaises(AudioPodError):
                load_book(self.write(name, text))
        with self.assertRaises(AudioPodError):
            load_book(self.root / 'missing.txt')

    def test_chunks_preserve_words_and_are_bounded(self):
        text = ('“Hello, world!”\n\nThis sentence has punctuation, contractions, and spaces. ' * 70).strip()
        chunks = list(split_text(text, 120))
        self.assertEqual(' '.join(text.split()), ' '.join(' '.join(chunks).split()))
        self.assertTrue(all(len(c) <= 120 for c in chunks))

    def test_unbroken_text_is_bounded_without_loss(self):
        text = '字' * 5000
        chunks = list(split_text(text, 100))
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(c) <= 100 for c in chunks))

    def test_chapter_range_validation(self):
        self.assertEqual(chapter_selection('1,3-5,3', 5), [0, 2, 3, 4])
        for value in ['0', '2-1', '6', '1-9999999999', 'NaN', '1,', '1-2-3']:
            with self.subTest(value=value), self.assertRaises(AudioPodError):
                chapter_selection(value, 5)


if __name__ == '__main__':
    unittest.main()
