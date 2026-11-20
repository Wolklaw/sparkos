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
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-snip-{var.lower()}-'))

from langcheck import clipped, table_problems  # noqa: E402,F401
from sparksnip import text as text  # noqa: E402
from sparksnip.lang import ui_language  # noqa: E402


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
            for key in ('btn.text',):
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
    """The main window in each mode, the result window in each state and the recording bar,
    with the longest text they show."""

    def setUp(self):
        from sparksnip import app as appmod
        from sparksnip.core import Monitor
        self.app = appmod.App(start_mode=None)
        self.monitor = Monitor('TEST-1', 0, 0, 1920, 1080)
        self.pump()

    def tearDown(self):
        try:
            self.app.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def pump(self, n=10):
        import time
        for _ in range(n):
            self.app.root.update()
            time.sleep(0.01)

    def test_main_window_fits_in_every_mode(self):
        for mode in ('text', 'image', 'video'):
            self.app.remember_mode(mode)
            self.pump()
            with self.subTest(mode=mode):
                self.assertEqual(clipped(self.app.root), [])
        self.app._button_state(True, text.t('btn.stop'))
        for key in ('status.share', 'status.reading', 'status.saving', 'status.error'):
            self.app._set_status(text.t(key), 'white')
            with self.subTest(status=key):
                self.assertEqual(clipped(self.app.root), [])

    def test_result_window_fits(self):
        from PIL import Image
        from sparksnip.core import OCRResult
        image = Image.new('RGB', (640, 200), 'white')
        result = OCRResult("Invoice 2041 due Friday", 62.0, 'plain')
        states = [('reading', lambda p: p.reading()),
                  ('text', lambda p: p.show_text(result, None)),
                  ('text refused', lambda p: p.show_text(result, 'no clipboard tool')),
                  ('image', lambda p: p.show_image(None)),
                  ('image refused', lambda p: p.show_image('no clipboard tool')),
                  ('empty', lambda p: p.show_empty()),
                  ('error', lambda p: p.show_error(text.t('fail.recording'),
                                                   text.t('rec.other_screen', screen='DP-1'))),
                  ('video', lambda p: p.show_video(__file__, 83.0, (1920, 1080), 'H.264 (GPU)',
                                                   text.t('audio.sound')))]
        for name, show in states:
            popup = self.app.open_popup(image, self.monitor)
            show(popup)
            self.pump()
            with self.subTest(state=name):
                self.assertEqual(clipped(popup), [])
            popup.destroy()

    def test_recording_bar_fits(self):
        from sparksnip.windows import RecordBar
        bar = RecordBar(self.app, (100, 300, 900, 800), self.monitor,
                        text.t('audio.sound') + ' + ' + text.t('audio.mic'), lambda: None)
        for step in (bar.waiting, lambda: bar.recording(83.0), bar.finishing):
            step()
            self.pump()
            with self.subTest(step=getattr(step, '__name__', 'recording')):
                self.assertEqual(clipped(bar), [])
        bar.close()
