"""The French interface: every sentence translated with the same blanks, every key the code asks
for exists, and the window's text fits. CI runs the suite twice, with SPARK_LANG=en and fr."""

import glob
import os
import re
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-clock-{var.lower()}-'))
os.environ['SPARK_CLOCK_REDUCED_MOTION'] = '1'

from langcheck import clipped, fields, table_problems  # noqa: E402
from sparkclock import text  # noqa: E402


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            for table in (text.EN, text.FR):
                filled = table[key].format(**{name: 'X' for name in fields(value)})
                self.assertNotIn('{', filled, key)

    def test_every_key_the_code_asks_for_exists(self):
        package = os.path.join(os.path.dirname(HERE), 'sparkclock')
        asked = set()
        for path in glob.glob(os.path.join(package, '*.py')):
            with open(path, encoding='utf-8') as f:
                asked |= set(re.findall(r"\bt\('([a-z_0-9]+\.[a-z_.0-9]*[a-z_0-9])'", f.read()))
        self.assertEqual(sorted(k for k in asked if k not in text.EN), [])
        from sparkclock import store
        for name in store.SOUNDS:
            self.assertIn('sound.' + name, text.EN)
        for name in ('alarms', 'timers', 'stopwatch', 'world'):
            self.assertIn('tab.' + name, text.EN)


def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class Fits(unittest.TestCase):
    def test_no_clipped_text_on_any_tab(self):
        from sparkclock import store
        from sparkclock.app import App
        store.update_config(lambda c: c['alarms'].append(
            {'time': '06:45', 'days': [0, 1, 2, 3, 4], 'label': 'Work', 'enabled': True}))
        store.add_timer(300, 'Tea')
        app = App(ask=lambda *a, **k: False, error=lambda *a, **k: None, start_service=False)
        self.addCleanup(app.close)
        app.root.geometry('860x700')

        def pump(seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                app.root.update()
                time.sleep(0.01)
        pump(0.6)
        for tab in ('alarms', 'timers', 'stopwatch', 'world'):
            app.show(tab)
            pump(0.4)
            self.assertEqual(clipped(app.root), [], tab)


if __name__ == '__main__':
    unittest.main()
