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
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-monitor-{var.lower()}-'))

from langcheck import clipped, table_problems  # noqa: E402,F401
from sparkmonitor import text as text  # noqa: E402
from sparkmonitor.lang import ui_language  # noqa: E402


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
            for key in ('tab.apps',):
                self.assertEqual(text.t(key), table[key])


try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    DISPLAY = True
except Exception:  # noqa: BLE001 - no display, or no Tk at all
    DISPLAY = False


def have_display() -> bool:
    if os.name == 'nt':
        return True
    return DISPLAY and bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        import shutil
        self.dir = tempfile.mkdtemp(prefix='spark-monitor-lang-')
        self.root = os.path.join(self.dir, 'root')
        shutil.copytree(os.path.join(HERE, 'fixtures', 'root'), self.root)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def pump(self, app, seconds):
        import time
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def test_text_fits_on_every_tab(self):
        from sparkmonitor.app import App
        from sparkmonitor.source import Source
        for tab in ('apps', 'performance', 'startup', 'details'):
            app = App(Source(self.root), tab=tab)
            try:
                self.pump(app, 0.8)
                app.root.geometry('%dx%d' % app.root.minsize())
                self.pump(app, 0.3)
                with self.subTest(tab=tab):
                    self.assertEqual(clipped(app.root), [])
                for key in ('status.paused', 'status.test_data', 'status.crashed'):
                    app.set_status(text.t(key), 'white')
                    with self.subTest(tab=tab, status=key):
                        self.assertEqual(clipped(app.root), [])
            finally:
                app.close()
