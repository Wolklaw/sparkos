"""Data, search, recents and settings. No display needed."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sparkemoji import cli, core, lang, text  # noqa: E402


class DataTest(unittest.TestCase):

    def test_sizes(self):
        groups = core.groups()
        emoji = [g for g in groups if g.kind == 'emoji']
        self.assertEqual([g.id for g in emoji],
                         ['smileys', 'people', 'nature', 'food', 'travel', 'activities',
                          'objects', 'symbols', 'flags'])
        self.assertGreater(sum(len(g.entries) for g in emoji), 1800)
        self.assertGreater(sum(len(g.entries) for g in groups if g.kind == 'symbol'), 300)

    def test_every_entry_has_both_names(self):
        for e in core.all_entries():
            self.assertTrue(e.char and e.name_en and e.name_fr, e)

    def test_symbol_groups_asked_for(self):
        ids = {g.id for g in core.groups() if g.kind == 'symbol'}
        self.assertTrue({'arrows', 'math', 'currency', 'letters'} <= ids)

    def test_skin_tones(self):
        wave = core.find_entry('\U0001F44B')
        self.assertEqual(len(wave.tones), 5)
        self.assertEqual(wave.with_tone(2), '\U0001F44B\U0001F3FD')
        self.assertEqual(wave.with_tone(-1), '\U0001F44B')
        self.assertEqual(core.find_entry(wave.tones[4]), wave)
        face = core.find_entry('\U0001F600')
        self.assertEqual(face.with_tone(3), face.char)        # no tones: unchanged

    def test_french_title(self):
        self.assertEqual(core.groups()[0].title('fr'), 'Visages et émotions')
        self.assertEqual(core.groups()[0].title('en'), 'Smileys and emotion')

    def test_no_empty_group(self):
        for g in core.groups():
            self.assertTrue(g.entries, g.id)


class SearchTest(unittest.TestCase):

    def first(self, query, n=5):
        return [e.char for e in core.search(query, limit=n)]

    def test_english_and_french_names(self):
        self.assertIn('\U0001F600', self.first('grinning face'))
        self.assertIn('\U0001F44D', self.first('thumbs up'))
        self.assertIn('\U0001F44D', self.first('pouce vers le haut'))
        self.assertIn('\U0001F436', self.first('chien', 10))
        self.assertIn('\U0001F436', self.first('dog', 10))

    def test_accents_and_case_do_not_matter(self):
        self.assertEqual(self.first('ÉTOILE'), self.first('etoile'))
        self.assertEqual(self.first('cœur'), self.first('coeur'))
        self.assertTrue(self.first('visage souriant'))

    def test_every_word_must_match(self):
        self.assertEqual(self.first('dog banana'), [])
        found = core.search('red heart')
        self.assertEqual(found[0].char, '❤️')

    def test_exact_name_first(self):
        self.assertEqual(core.search('euro')[0].char, '€')

    def test_symbols(self):
        self.assertIn('→', self.first('flèche droite', 10))
        self.assertIn('→', self.first('right arrow', 40))
        self.assertIn('é', self.first('e accent aigu'))
        self.assertIn('ç', self.first('cédille', 10))
        self.assertIn('≠', self.first('not equal', 10))
        self.assertIn('£', self.first('pound', 10) + self.first('livre', 10))
        self.assertIn('©', self.first('copyright'))

    def test_by_code_and_by_character(self):
        self.assertEqual(self.first('U+1F44D'), ['\U0001F44D'])
        self.assertEqual(self.first('0x20ac'), ['€'])
        self.assertEqual(self.first('€'), ['€'])
        self.assertEqual(self.first('U+zzzz'), [])

    def test_flags_and_keycaps(self):
        self.assertIn('\U0001F1E8\U0001F1E6', self.first('drapeau canada'))
        self.assertIn('\U0001F1EB\U0001F1F7', self.first('flag france'))

    def test_empty_and_nonsense(self):
        self.assertEqual(core.search(''), [])
        self.assertEqual(core.search('   '), [])
        self.assertEqual(core.search('qzxqzxqzx'), [])

    def test_limit(self):
        self.assertEqual(len(core.search('face', limit=7)), 7)


class StateTest(unittest.TestCase):

    def test_recents(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'r.json')
            self.assertEqual(core.load_recents(path), [])
            core.add_recent('a', path)
            core.add_recent('b', path)
            self.assertEqual(core.add_recent('a', path), ['a', 'b'])
            for i in range(60):
                core.add_recent(f'x{i}', path)
            self.assertEqual(len(core.load_recents(path)), core.RECENT_MAX)
            self.assertEqual(core.load_recents(path)[0], 'x59')

    def test_recents_ignores_junk(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'r.json')
            with open(path, 'w') as f:
                f.write('{"not": "a list"}')
            self.assertEqual(core.load_recents(path), [])
            with open(path, 'w') as f:
                f.write(json.dumps(['ok', 5, None, 'x' * 100]))
            self.assertEqual(core.load_recents(path), ['ok'])

    def test_settings(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 's.json')
            self.assertEqual(core.load_settings(path), core.DEFAULTS)
            self.assertTrue(core.save_settings({'tone': 3, 'paste': True, 'portal_token': 'abc',
                                                'bogus': 1}, path))
            got = core.load_settings(path)
            self.assertEqual((got['tone'], got['paste'], got['portal_token']), (3, True, 'abc'))
            self.assertNotIn('bogus', got)
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), '0o600')

    def test_settings_clean_bad_values(self):
        got = core.clean_settings({'tone': 9, 'paste': 'yes', 'portal_token': 5, 'glitch': 1})
        self.assertEqual(got, core.DEFAULTS)
        self.assertEqual(core.clean_settings([1, 2]), core.DEFAULTS)


class LanguageTest(unittest.TestCase):

    def test_language(self):
        self.assertEqual(lang.ui_language({'SPARK_LANG': 'fr'}), 'fr')
        self.assertEqual(lang.ui_language({'LANG': 'fr_CA.UTF-8'}), 'fr')
        self.assertEqual(lang.ui_language({'LANG': 'en_US.UTF-8'}), 'en')

    def test_same_keys_in_both_languages(self):
        self.assertEqual(set(text.EN), set(text.FR))
        for key, value in text.EN.items():
            import re
            self.assertEqual(set(re.findall(r'{(\w+)}', value)),
                             set(re.findall(r'{(\w+)}', text.FR[key])), key)

    def test_t_fills_blanks(self):
        self.assertIn('x', text.t('status.pasted', char='x'))


class CliTest(unittest.TestCase):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def run_app(self, *args):
        return subprocess.run([sys.executable, os.path.join(self.here, 'spark_emoji.py'), *args],
                              capture_output=True, text=True, timeout=60)

    def test_version(self):
        out = self.run_app('--version')
        self.assertEqual(out.stdout.strip(), cli.version_line())

    def test_search_prints_char_and_both_names(self):
        out = self.run_app('--search', 'sourire', '--limit', '3')
        self.assertEqual(out.returncode, 0)
        first = out.stdout.splitlines()[0].split('\t')
        self.assertEqual(len(first), 3)

    def test_search_nothing_exits_1(self):
        self.assertEqual(self.run_app('--search', 'qzxqzxqzx').returncode, 1)


if __name__ == '__main__':
    unittest.main()
