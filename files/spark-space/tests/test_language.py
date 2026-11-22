"""The French interface: every sentence translated with the same blanks, and text that fits.
CI runs the whole suite twice, with SPARK_LANG=en and fr."""

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-space-{var.lower()}-'))
os.environ['SPARK_SPACE_REDUCED_MOTION'] = '1'

from langcheck import clipped, fields, table_problems  # noqa: E402
from sparkspace import text  # noqa: E402
from sparkspace.kinds import KINDS  # noqa: E402


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            for table in (text.EN, text.FR):
                filled = table[key].format(**{name: 'X' for name in fields(value)})
                self.assertNotIn('{', filled, key)

    def test_every_reason_hint_and_kind_has_words(self):
        for reason in ('d_drive', 'protected', 'in_trash', 'read_only', 'windows_system',
                       'gone', 'not_writable'):
            self.assertIn('refuse.' + reason, text.EN)
        for key in ('cache', 'trash', 'flatpak', 'containers', 'journal', 'shadercache',
                    'steam_downloading', 'app_cache'):
            self.assertIn(f'hint.{key}.title', text.EN)
            self.assertIn(f'hint.{key}.body', text.EN)
        for kind in KINDS:
            self.assertIn('kind.' + kind, text.EN)


def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class Fits(unittest.TestCase):
    def test_no_clipped_text(self):
        from sparkspace.app import App
        tmp = tempfile.mkdtemp(prefix='spark-space-fits-')
        self.addCleanup(shutil.rmtree, tmp, True)
        for name, size in (('videos/film.mkv', 900_000), ('docs/a.txt', 1000)):
            path = os.path.join(tmp, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(b'\1' * size)
        app = App(opener=lambda argv: True, ask=lambda *a, **k: False, tell=lambda *a, **k: None,
                  warn=lambda *a, **k: None, error=lambda *a, **k: None)
        self.addCleanup(app.close)
        app.root.geometry('1180x760')

        def pump(seconds, until=None):
            end = time.monotonic() + seconds
            while time.monotonic() < end and not (until and until()):
                app.root.update()
                time.sleep(0.01)
        pump(1)
        self.assertEqual(clipped(app.root), [], "start screen")
        app.scan(tmp)
        pump(10, until=lambda: app.screen is app.results)
        pump(0.3)
        r = app.results
        r.select(r.current.sorted_children()[0])
        for tab in r.TABS:
            r.set_tab(tab)
            pump(1, until=lambda: tab not in ('largest', 'types') or r.summary is not None)
            self.assertEqual(clipped(app.root), [], tab)


if __name__ == '__main__':
    unittest.main()
