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
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-edit-{var.lower()}-'))

from langcheck import clipped, table_problems  # noqa: E402,F401
from sparkedit import text as text  # noqa: E402
from sparkedit.lang import ui_language  # noqa: E402


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
            for key in ('untitled',):
                self.assertEqual(text.t(key), table[key])


try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    DISPLAY = True
except Exception:  # noqa: BLE001 - no display, or no Tk at all
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        os.environ['SPARK_EDIT_REDUCED_MOTION'] = '1'
        from sparkedit.app import App
        self.app = App([], restore=False)
        self.app.root.update()
        self.start_clipped = clipped(self.app.root)
        self.app.new_buffer()

    def tearDown(self):
        try:
            for buf in self.app.buffers:
                buf.text.edit_modified(False)
            self.app.quit()
        except Exception:  # noqa: BLE001
            pass

    def test_text_fits(self):
        app, root = self.app, self.app.root
        self.assertEqual(self.start_clipped, [], "start screen")
        root.geometry('980x680')                 # the size a new window opens at
        for mode in ('find', 'replace', 'goto'):
            app.find(mode)
            with self.subTest(bar=mode):
                self.assertEqual(clipped(root), [])
        for key in ('status.admin_wait', 'status.read_only_fs', 'status.copied',
                    'status.read_only', 'error.cancelled'):
            app.status(text.t(key))
            with self.subTest(status=key):
                self.assertEqual(clipped(root), [])

    def test_long_messages_leave_the_status_items_alone(self):
        app, root = self.app, self.app.root
        root.geometry('980x680')
        app.status(text.t('status.huge', name='very-long-file-name.log'))
        root.update()
        problems = [p for p in clipped(root) if 'statusitem' in p]
        self.assertEqual(problems, [])
