"""The French interface: every sentence translated with the same blanks, the language taken
from the PC, and text that fits. The whole suite runs twice in CI, with SPARK_LANG=en and fr."""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-files-{var.lower()}-'))
os.environ['SPARK_FILES_REDUCED_MOTION'] = '1'

from langcheck import clipped, fields, table_problems  # noqa: E402
from sparkfiles import text  # noqa: E402
from sparkfiles.lang import ui_language  # noqa: E402


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            names = {name: 'X' for name in fields(value)}
            for table in (text.EN, text.FR):
                filled = table[key].format(**names)
                self.assertNotIn('{', filled.replace('{{', ''), key)

    def test_singular_forms(self):
        self.assertEqual(text.EN['status.items.1'].format(n=1), "1 item")
        if text.LANG == 'fr':
            self.assertEqual(text.t('status.items', n=0), "0 élément")
            self.assertEqual(text.t('status.items', n=2), "2 éléments")
        else:
            self.assertEqual(text.t('status.items', n=0), "0 items")
            self.assertEqual(text.t('status.items', n=1), "1 item")


class PickTheLanguage(unittest.TestCase):
    def test_from_the_locale(self):
        cases = [({'LANG': 'fr_CA.UTF-8'}, 'fr'), ({'LANG': 'en_CA.UTF-8'}, 'en'),
                 ({'LC_MESSAGES': 'fr_FR.UTF-8', 'LANG': 'en_US.UTF-8'}, 'fr'),
                 ({'LC_ALL': 'en_US.UTF-8', 'LC_MESSAGES': 'fr_CA.UTF-8'}, 'en'),
                 ({}, 'en'), ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'}, 'en'),
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
    _probe = tk.Tk()
    _probe.destroy()
    DISPLAY = True
except Exception:  # noqa: BLE001
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "needs a display")
class Fits(unittest.TestCase):
    """Nothing in the window, the jobs panel or the dialogs is cut off, in either language."""

    def setUp(self):
        from sparkfiles.app import App
        self.dir = tempfile.mkdtemp(prefix='spark-files-fit-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        for n in ('a.txt', 'b.png'):
            open(os.path.join(self.dir, n), 'w').close()
        self.app = App()
        self.app.quit = lambda: None
        self.w = self.app.new_window(self.dir)
        self.w.geometry('1100x700')
        for _ in range(20):
            self.app.root.update()

    def tearDown(self):
        self.app.shutdown()

    def test_window_fits(self):
        self.assertEqual(clipped(self.w), [])

    def test_dialogs_fit(self):
        from sparkfiles.dialogs import BatchRename, OpenWith, Properties
        from sparkfiles.jobs import ClashDialog
        from sparkfiles.netdialogs import ConnectDialog
        from sparkfiles.ops import Job
        paths = [os.path.join(self.dir, n) for n in ('a.txt', 'b.png')]
        job = Job('copy', paths, self.dir)
        for d in (Properties(self.app, self.w, paths[:1]),
                  BatchRename(self.app, self.w, paths, lambda *_a: None),
                  OpenWith(self.app, self.w, paths[:1]),
                  ClashDialog(self.app, self.w, job, paths[0], paths[0]),
                  ConnectDialog(self.app, self.w)):
            d.place_and_show()
            for _ in range(10):
                self.app.root.update()
            self.assertEqual(clipped(d), [], type(d).__name__)
            d.destroy()

    def test_jobs_panel_fits(self):
        from sparkfiles.ops import Job
        job = Job('copy', [os.path.join(self.dir, 'a.txt')], self.dir)
        self.w.jobs.add(job)
        for _ in range(10):
            self.app.root.update()
        self.assertEqual(clipped(self.w.jobs), [])


if __name__ == '__main__':
    unittest.main()
