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
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-update-{var.lower()}-'))

from langcheck import clipped, table_problems  # noqa: E402,F401
from sparkupdate import text as text  # noqa: E402
from sparkupdate.lang import ui_language  # noqa: E402


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
            for key in ('btn.check',):
                self.assertEqual(text.t(key), table[key])


try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    DISPLAY = True
except Exception:  # noqa: BLE001 - no display, or no Tk at all
    DISPLAY = False


class Dates(unittest.TestCase):
    def test_when_and_day_follow_the_language(self):
        import time
        from sparkupdate import core
        now = time.mktime((2026, 11, 20, 15, 0, 0, 0, 0, -1))
        today = time.mktime((2026, 11, 20, 4, 12, 0, 0, 0, -1))
        yesterday = time.mktime((2026, 11, 19, 22, 5, 0, 0, 0, -1))
        earlier = time.mktime((2026, 11, 17, 4, 12, 0, 0, 0, -1))
        got = [core.when(today, now), core.when(yesterday, now), core.when(earlier, now),
               core.when(None), core.day(earlier)]
        want = {'en': ['today 04:12', 'yesterday 22:05', 'Nov 17 04:12', 'never',
                       'Nov 17, 2026'],
                'fr': ["aujourd'hui à 04:12", 'hier à 22:05', 'le 17 nov. à 04:12', 'jamais',
                       '17 nov. 2026']}[text.LANG]
        self.assertEqual(got, want)

    def test_twelve_months(self):
        for table in (text.EN, text.FR):
            self.assertEqual(len(table['months'].split()), 12)


class WaitReasons(unittest.TestCase):
    def test_the_window_says_it_in_its_own_language(self):
        """The background run saves the English for the log and the key for the window."""
        from sparkupdate import guard
        from sparkupdate.core import Env
        env = Env(tempfile.mkdtemp())
        original = guard.game_running
        guard.game_running = lambda _env: 'Hades'
        try:
            self.assertEqual(guard.wait_reason(env), ('wait.game', {'game': 'Hades'}))
            self.assertEqual(guard.reason_to_wait(env), 'a game is running (Hades)')
        finally:
            guard.game_running = original


def have_display() -> bool:
    if os.name == 'nt':
        return True
    return DISPLAY and bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class Window(unittest.TestCase):
    def open(self, status_file, updater_on):
        import gc
        import time
        from test_spark_update import make_root
        from sparkupdate.app import App
        from sparkupdate.core import Env
        app = App(Env(make_root(status_file, updater_on)))

        def close():
            while app.pending:
                app.root.update()
                time.sleep(0.01)
            app.root.destroy()
            app.__dict__.clear()
            gc.collect()
        self.addCleanup(close)
        deadline = time.monotonic() + 15
        while app.snap is None and time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.02)
        app.root.geometry('%dx%d' % app.root.minsize())
        for _ in range(5):
            app.root.update()
            time.sleep(0.02)
        return app

    def test_text_fits_on_every_page(self):
        for status_file, updater_on in (('rpm-ostree-staged.json', 'uupd'),
                                        ('rpm-ostree-rollback-queued.json', 'spark'),
                                        ('rpm-ostree-none.json', 'spark')):
            app = self.open(status_file, updater_on)
            for page in ('main', 'settings', 'log'):
                app.show(page, glitch=False)
                with self.subTest(status=status_file, page=page):
                    self.assertEqual(clipped(app.root), [])
            app.show('main', glitch=False)
            for key in ('status.ready', 'status.rolled_back', 'status.no_image',
                        'status.failed', 'status.flatpak'):
                app.status.config(text='● ' + text.t(key))
                with self.subTest(status=key):
                    self.assertEqual(clipped(app.root), [])
