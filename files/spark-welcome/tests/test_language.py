"""The French interface: every sentence translated with the same blanks, the language taken
from the PC, and text that fits. The whole suite runs twice in CI, with SPARK_LANG=en and fr."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-welcome-{var.lower()}-'))

from langcheck import clipped, table_problems  # noqa: E402,F401
from sparkwelcome import strings as text  # noqa: E402
from sparkwelcome.lang import ui_language  # noqa: E402


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        """t() with made-up values for every blank: no KeyError, no blank named like t()'s
        own argument, no leftover braces."""
        from langcheck import fields
        for key, value in text.EN.items():
            filled = text.t(key, **{name: 'X' for name in fields(value)})
            self.assertNotIn('{', filled.replace('{{', ''), key)
            for table in (text.EN, text.FR):
                table[key].format(**{name: 'X' for name in fields(value)})


class PickTheLanguage(unittest.TestCase):
    def test_from_the_locale(self):
        cases = [({'LANG': 'fr_CA.UTF-8'}, 'fr'), ({'LANG': 'en_CA.UTF-8'}, 'en'),
                 ({'LC_MESSAGES': 'fr_FR.UTF-8', 'LANG': 'en_US.UTF-8'}, 'fr'),
                 ({'LC_ALL': 'en_US.UTF-8', 'LC_MESSAGES': 'fr_CA.UTF-8'}, 'en'),
                 ({'LC_ALL': 'fr_CA'}, 'fr'), ({'LANG': 'C.UTF-8'}, 'en'), ({}, 'en'),
                 ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'}, 'en'),
                 ({'LANG': 'C', 'SPARK_LANG': 'fr'}, 'fr'),
                 ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'de'}, 'fr')]
        for env, want in cases:
            with self.subTest(env=env):
                self.assertEqual(ui_language(env), want)

    def test_spark_lang_picks_the_table(self):
        want = os.environ.get('SPARK_LANG')
        if want in ('en', 'fr'):
            self.assertEqual(text.LANG, want)
            table = text.FR if want == 'fr' else text.EN
            for key in ('nav.next',):
                self.assertEqual(text.t(key), table[key])


try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    DISPLAY = True
except Exception:  # noqa: BLE001 - no display, or no Tk at all
    DISPLAY = False


class Catalog(unittest.TestCase):
    def test_every_app_has_its_french(self):
        from sparkwelcome import catalog
        cat = catalog.load()
        for entry in cat.all():
            self.assertTrue(entry.blurb_fr, entry.id)
        for category in cat.categories:
            self.assertTrue(category.name_fr, category.name)


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(unittest.TestCase):
    def test_text_fits_on_every_page(self):
        import time
        from unittest import mock
        import sparkwelcome
        from sparkwelcome.app import App
        config = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': config}):
            app = App()
            try:
                def pump(seconds, until=None):
                    end = time.time() + seconds
                    while time.time() < end and not (until and until()):
                        app.root.update()
                        time.sleep(0.02)
                pump(0.3)
                app.root.geometry('%dx%d' % app.root.minsize())
                pump(0.3)
                for name in sparkwelcome.PAGES:
                    app.go(name)
                    pump(0.3)
                    if name == 'checks':
                        page = app.pages['checks']
                        pump(60, until=lambda: not page.running)
                        pump(0.2)
                    with self.subTest(page=name):
                        self.assertEqual(clipped(app.root), [])
            finally:
                app.close()
