"""The French interface: every sentence translated with the same blanks, the language taken
from the PC, and text that fits in every state. CI runs the suite twice, SPARK_LANG=en and fr."""

import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import fontkit  # noqa: E402,F401  (first: it points HOME at a temporary folder)
from fontkit import HAVE_FC, TMP, fresh_home, pick_font, rename_family  # noqa: E402
from langcheck import clipped, fields, table_problems  # noqa: E402

from sparkfonts import core, fcdata, text, winfonts  # noqa: E402
from sparkfonts.core import count, human_size  # noqa: E402
from sparkfonts.lang import ui_language  # noqa: E402


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            for table in (text.EN, text.FR):
                filled = table[key].format(**{name: 'X' for name in fields(value)})
                self.assertNotIn('{', filled, key)

    def test_the_dynamic_keys_exist(self):
        for family, names in (
                ('cat.', fcdata.CATEGORIES), ('lang.', fcdata.LANGUAGES),
                ('why.', ('not_font', 'web_font', 'unreadable', 'no_fonts', 'too_many')),
                ('why_locked.', ('system', 'local', 'flatpak', 'other')),
                ('win.problem.', ('generic', 'no_drive', 'no_fonts'))):
            for name in names:
                self.assertIn(family + name, text.EN, family + name)

    def test_french_differs_from_english(self):
        same = [k for k, v in text.EN.items() if text.FR[k] == v and len(v) > 25]
        self.assertEqual(same, [], "long sentences left in English")


class PickTheLanguage(unittest.TestCase):
    def test_from_the_locale(self):
        cases = [({'LANG': 'fr_CA.UTF-8'}, 'fr'), ({'LANG': 'en_CA.UTF-8'}, 'en'),
                 ({'LC_MESSAGES': 'fr_FR.UTF-8', 'LANG': 'en_US.UTF-8'}, 'fr'),
                 ({'LC_ALL': 'en_US.UTF-8', 'LC_MESSAGES': 'fr_CA.UTF-8'}, 'en'),
                 ({'LANG': 'C.UTF-8'}, 'en'), ({}, 'en'),
                 ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'}, 'en'),
                 ({'LANG': 'C', 'SPARK_LANG': 'fr'}, 'fr')]
        for env, want in cases:
            with self.subTest(env=env):
                self.assertEqual(ui_language(env), want)

    def test_spark_lang_picks_the_table(self):
        want = os.environ.get('SPARK_LANG')
        if want in ('en', 'fr'):
            self.assertEqual(ui_language(), want)
            table = text.FR if want == 'fr' else text.EN
            self.assertEqual(text.t('btn.install'), table['btn.install'])

    def test_numbers_and_sizes_follow_the_language(self):
        if ui_language() == 'fr':
            self.assertEqual(count(12345), '12 345')
            self.assertIn('Ko' if 'Ko' in human_size(2048) else 'KB', human_size(2048))
        else:
            self.assertEqual(count(12345), '12,345')
            self.assertEqual(human_size(1536), '1.5 KB')


def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display() and HAVE_FC, "needs a display and fontconfig")
class Fits(unittest.TestCase):
    """No text is cut off in this language, in the states where the sentences are longest."""

    def test_no_clipped_text(self):
        from sparkfonts.app import App
        fresh_home()
        font = pick_font()
        if not font:
            self.skipTest("no TrueType or OpenType font on this system")
        work = tempfile.mkdtemp(prefix='fits-', dir=TMP)
        mine = os.path.join(work, 'mine.ttf')
        rename_family(font, mine, 'Zf' + 'x' * 30)
        junk = os.path.join(core.fonts_dir(), 'Junk')
        os.makedirs(junk)
        with open(os.path.join(junk, 'broken.ttf'), 'wb') as f:
            f.write(b'not a font')
        root = os.path.join(work, 'drive')
        os.makedirs(os.path.join(root, 'Windows', 'Fonts'))
        rename_family(font, os.path.join(root, 'Windows', 'Fonts', 'W.TTF'), 'Zg' + 'x' * 30)
        app = App(files=[mine], opener=lambda argv: True, ask=lambda *a, **k: False,
                  tell=lambda *a, **k: None, warn=lambda *a, **k: None,
                  error=lambda *a, **k: None,
                  windows_finder=lambda: (winfonts.windows_sources(root), ''))
        self.addCleanup(app.close)
        app.root.geometry('1180x760')

        def pump(seconds, until=None):
            end = time.monotonic() + seconds
            while time.monotonic() < end and not (until and until()):
                app.root.update()
                time.sleep(0.01)
            app.root.update()
        pump(20, until=lambda: app.scope == 'opened' and app.busy == 0)
        pump(0.5)
        self.assertEqual(app.scope, 'opened')
        for tab in ('preview', 'chars', 'details'):
            app.set_tab(tab)
            pump(1.2)
            self.assertEqual(clipped(app.root), [], f"opened, {tab}")
        app.set_scope('all')
        pump(0.3)
        app.select_family(app.view[0].name)
        for tab in ('preview', 'chars', 'details'):
            app.set_tab(tab)
            pump(1.2)
            self.assertEqual(clipped(app.root), [], f"system font, {tab}")
        app.set_scope('broken')
        pump(0.5)
        self.assertEqual(clipped(app.root), [], "broken")
        app.set_scope('all')
        app.search_var.set('zzzz no such font')
        pump(0.6)
        self.assertEqual(clipped(app.root), [], "nothing found")
        app.search_var.set('')
        pump(0.4)
        app.windows_dialog()
        dialog = app.windows
        pump(15, until=lambda: bool(dialog.tree.get_children()))
        self.assertEqual(clipped(dialog), [], "windows dialog")
        dialog.close()
        # a narrow window, the smallest the app allows
        app.root.geometry(f"{app.px(900)}x{app.px(580)}")
        pump(0.8)
        self.assertEqual(clipped(app.root), [], "smallest window")


if __name__ == '__main__':
    unittest.main()
