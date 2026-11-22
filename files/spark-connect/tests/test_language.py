"""The French interface: every sentence translated with the same blanks, and text that fits.
CI runs the whole suite twice, with SPARK_LANG=en and fr."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'APPDATA', 'LOCALAPPDATA'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-connect-{var.lower()}-'))
os.environ['SPARK_CONNECT_REDUCED_MOTION'] = '1'

from langcheck import clipped, fields, table_problems  # noqa: E402
from sparkconnect import text  # noqa: E402


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            for table in (text.EN, text.FR):
                filled = table[key].format(**{name: 'X' for name in fields(value)})
                self.assertNotIn('{', filled, key)


def have_display() -> bool:
    return os.name == 'nt' or bool(os.environ.get('DISPLAY') or
                                   os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class Fits(unittest.TestCase):
    def test_no_clipped_text(self):
        import test_spark_connect as tsc
        from sparkconnect.app import App
        app = App(config_path=tsc.EXAMPLE,
                  transport=tsc.FakeTransport({'Main server': 'failed-unit.json',
                                               'Standby laptop': 'standby-takeover.json'}),
                  site_checker=tsc.fake_site, auto_refresh=False, notifier=lambda a, b: True)
        self.addCleanup(app.close)
        app.root.geometry('1060x720')
        for m in app.config.machines:
            app.start(('machine', m.name))
        for s in app.config.sites:
            app.start(('site', s.name))
        import time
        end = time.monotonic() + 5
        while (app.pending or len(app.results) < 2) and time.monotonic() < end:
            app.root.update()
            time.sleep(0.02)
        self.assertEqual(clipped(app.root), [])
        for name in ('Main server', 'Standby laptop'):
            app.open_machine(name)
            for tab in app.machine_view.tabbar.labels:
                app.machine_view.show(tab)
                self.assertEqual(clipped(app.root), [], f"{name} {tab}")
            app.show_overview()


if __name__ == '__main__':
    unittest.main()
