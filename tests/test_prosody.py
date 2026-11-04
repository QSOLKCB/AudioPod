import re
import unittest

from audiopod.prosody import phrases


class PhraseTests(unittest.TestCase):
    def test_titles_decimals_and_attributed_dialogue_stay_together(self):
        text = 'Dr. Morgan measured 3.14 metres. “Is that right?” she asked.\n\nMr. Lee nodded.'
        parts = list(phrases(text))
        self.assertEqual([p.text for p in parts], [
            'Dr. Morgan measured 3.14 metres.', '“Is that right?” she asked.', 'Mr. Lee nodded.'])
        self.assertEqual([p.boundary for p in parts], ['sentence', 'paragraph', 'end'])

    def test_acronyms_domains_and_unicode_stops(self):
        text = 'Visit example.org with the U.S. team. 好！次。 Next… Done!'
        self.assertEqual([p.text for p in phrases(text)], [
            'Visit example.org with the U.S. team.', '好！', '次。', 'Next…', 'Done!'])

    def test_bounded_planning_preserves_every_non_whitespace_character(self):
        sources = [
            '  One\r\n\r\n Two.\n\n\nThree!\n\n ',
            'A long sentence, ' * 150 + 'with an ending.',
            'word ' * 1000, '字' * 2000, 'x' * 2100,
            'a. ' * 1500, '— “?” ... ! \t ' * 300,
        ]
        for text in sources:
            with self.subTest(text=text[:40]):
                parts = list(phrases(text, limit=80))
                self.assertTrue(all(0 < len(p.text) <= 80 for p in parts))
                self.assertEqual(re.sub(r'\s', '', ''.join(p.text for p in parts)), re.sub(r'\s', '', text))
                self.assertEqual(parts[-1].boundary, 'end')

    def test_long_sentences_prefer_clauses_then_whitespace(self):
        parts = list(phrases('A patient narrator pauses here, then continues with a longer explanation ' * 3, limit=64))
        self.assertEqual(parts[0].text, 'A patient narrator pauses here,')
        self.assertEqual(parts[0].boundary, 'clause')
        self.assertEqual(next(phrases('word ' * 40, limit=64)).boundary, 'continuation')

    def test_empty_and_invalid_limits(self):
        for text in ('', ' \t\n\n '):
            self.assertEqual(list(phrases(text)), [])
        for limit in (0, 31, True, 600.0):
            with self.assertRaises(ValueError):
                list(phrases('hello', limit))
