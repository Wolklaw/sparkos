"""The French interface: every sentence translated with the same blanks, and text that fits.
CI runs the whole suite twice, with SPARK_LANG=en and fr."""

import atexit
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
TMP_HOME = tempfile.mkdtemp(prefix='spark-camera-langhome-')
os.environ['HOME'] = TMP_HOME
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.pop(var, None)
os.environ['SPARK_CAMERA_FAKE'] = '1'
os.environ['SPARK_CAMERA_REDUCED_MOTION'] = '1'

from langcheck import clipped, fields, table_problems  # noqa: E402
from sparkcamera import media, text  # noqa: E402


atexit.register(shutil.rmtree, TMP_HOME, True)


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            for table in (text.EN, text.FR):
                filled = table[key].format(**{name: 'X' for name in fields(value)})
                self.assertNotIn('{', filled, key)


def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
@unittest.skipIf(media.init(), "GStreamer is not available")
class Fits(unittest.TestCase):
    def test_no_clipped_text(self):
        from sparkcamera.app import App
        app = App(opener=lambda argv: True, ask=lambda *a, **k: False, tell=lambda *a, **k: None,
                  warn=lambda *a, **k: None, error=lambda *a, **k: None)
        self.addCleanup(app.close)
        app.root.geometry('1120x780')

        def pump(seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                app.root.update()
                time.sleep(0.01)
        pump(1.5)
        self.assertEqual(clipped(app.root), [], "camera tab")
        app.cam.set_kind('video')
        pump(0.3)
        self.assertEqual(clipped(app.root), [], "camera tab, video")
        app.pick_tab('voice')
        pump(1)
        self.assertEqual(clipped(app.root), [], "voice tab")


if __name__ == '__main__':
    unittest.main()
