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
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-link-{var.lower()}-'))

from langcheck import clipped, table_problems  # noqa: E402,F401
from sparklink import text as text  # noqa: E402
from sparklink.lang import ui_language  # noqa: E402


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
            for key in ('dev.ring',):
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
    """The window at its smallest, on each tab, with the test service from test_ui."""

    def test_text_fits_on_every_tab(self):
        import copy
        import time
        from test_ui import STATUS, FakeControl
        os.environ['SPARK_LINK_REDUCED_MOTION'] = '1'
        from sparklink.app import App
        ctl = FakeControl(copy.deepcopy(STATUS))
        app = App(tab='devices', control=ctl, poll=False)

        def pump(secs=0.3):
            end = time.monotonic() + secs
            while time.monotonic() < end:
                app.worker.pump()
                app.root.update()
                time.sleep(0.01)
        try:
            app.apply_status(ctl.request({'cmd': 'status'}))
            app.root.geometry('%dx%d' % app.root.minsize())
            pump()
            for tab in ('devices', 'pair', 'features'):
                app.show(tab)
                pump()
                with self.subTest(tab=tab):
                    self.assertEqual(clipped(app.root), [])
            ctl.request({'cmd': 'pair.start'})
            app.apply_status(ctl.request({'cmd': 'status'}))
            pump()
            with self.subTest(tab='pair', showing='code'):
                self.assertEqual(clipped(app.root), [])
            st = ctl.request({'cmd': 'status'})
            st['transfers'].append({'key': 'b:in:12', 'device': 'b' * 32, 'direction': 'in',
                                    'name': 'vacation-photos-2026.zip', 'size': 1500000000,
                                    'done': 0, 'state': 'waiting', 'reason': '', 'path': ''})
            app.apply_status(st)
            pump()
            with self.subTest(prompt='incoming file'):
                self.assertEqual(clipped(app.root), [])
            app.apply_status(None, running=False)
            pump()
            with self.subTest(service='stopped'):
                self.assertEqual(clipped(app.root), [])
        finally:
            app.destroy()
