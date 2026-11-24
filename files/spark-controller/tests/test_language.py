"""The French interface: every sentence translated with the same blanks, the language taken
from the PC, and text that fits. The whole suite runs twice in CI, with SPARK_LANG=en and fr."""

import os
import re
import shutil
import tempfile
import time
import unittest

import support
from langcheck import clipped, fields, table_problems
from sparkcontroller import text
from sparkcontroller.lang import ui_language
from sparkcontroller.hwmon import Hwmon

PKG = os.path.join(os.path.dirname(support.HERE), 'sparkcontroller')


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            filled = text.t(key, **{name: 'X' for name in fields(value)})
            self.assertNotIn('{', filled.replace('{{', ''), key)

    def test_every_key_used_in_the_code_exists(self):
        used = set()
        for name in os.listdir(PKG):
            if name.endswith('.py') and name != 'text.py':
                with open(os.path.join(PKG, name), encoding='utf-8') as f:
                    used.update(re.findall(r"\bt\(\s*['\"]([a-z0-9_.]+)['\"]", f.read()))
        self.assertEqual(sorted(k for k in used if k not in text.EN), [])


class PickTheLanguage(unittest.TestCase):
    def test_from_the_locale(self):
        cases = [({'LANG': 'fr_CA.UTF-8'}, 'fr'), ({'LANG': 'en_CA.UTF-8'}, 'en'),
                 ({'LANG': 'C.UTF-8'}, 'en'), ({}, 'en'),
                 ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'}, 'en'),
                 ({'LANG': 'C', 'SPARK_LANG': 'fr'}, 'fr')]
        for env, want in cases:
            with self.subTest(env=env):
                self.assertEqual(ui_language(env), want)

    def test_spark_lang_picks_the_table(self):
        want = os.environ.get('SPARK_LANG')
        if want in ('en', 'fr'):
            self.assertEqual(text.LANG, want)


try:
    import tkinter as tk
    tk.Tk().destroy()
    DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
except Exception:  # noqa: BLE001 - no display, or no Tk at all
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-controller-window-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.tree = os.path.join(self.dir, 'hwmon')
        support.fake_tree(self.tree)
        os.environ['XDG_CONFIG_HOME'] = os.path.join(self.dir, 'config')
        os.environ['SPARK_CONTROLLER_CONFIG'] = os.path.join(self.dir, 'fans.json')
        self.addCleanup(os.environ.pop, 'SPARK_CONTROLLER_CONFIG', None)

    def pump(self, app, seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def test_every_tab_opens_and_its_text_fits(self):
        from sparkcontroller.app import App
        for tab in ("overview", "fans", "rgb", "mouse", "pads", "drivers"):
            app = App(Hwmon(self.tree), tab=tab, use_usb=False)
            try:
                self.pump(app, 0.8)
                app.root.geometry('%dx%d' % app.root.minsize())
                self.pump(app, 0.3)
                with self.subTest(tab=tab):
                    self.assertEqual(clipped(app.root), [])
            finally:
                app.close()


if __name__ == '__main__':
    unittest.main()
