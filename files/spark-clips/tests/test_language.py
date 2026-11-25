"""The French interface: every sentence translated with the same blanks, and text that fits.
CI runs the whole suite twice, with SPARK_LANG=en and fr."""

import time
import unittest

import testenv
from langcheck import clipped, fields, table_problems
from sparkclips import text


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            for table in (text.EN, text.FR):
                filled = table[key].format(**{name: 'X' for name in fields(value)})
                self.assertNotIn('{', filled, key)

    def test_every_key_the_code_asks_for_exists(self):
        import os
        import re
        folder = os.path.join(testenv.HERE, '..', 'sparkclips')
        asked = set()
        for name in os.listdir(folder):
            if name.endswith('.py') and name != 'text.py':
                with open(os.path.join(folder, name), encoding='utf-8') as f:
                    asked |= set(re.findall(r"\bt\('([a-z_]+\.[a-z_0-9]+)'", f.read()))
        self.assertEqual(sorted(k for k in asked if k not in text.EN), [])
        # the keys built from a state, a problem, a size or a tool name
        for prefix, names in (('state.', ('off', 'waiting', 'starting', 'recording',
                                          'needs_setup', 'error', 'service_off')),
                              ('problem.', ('missing', 'no_hevc', 'no_encoder', 'ram', 'portal',
                                            'pipeline', 'not_recording', 'too_early',
                                            'save_failed')),
                              ('size.', ('native', '1080', '720')),
                              ('tool.', ('play', 'trim', 'rename', 'delete', 'copy', 'folder'))):
            for name in names:
                self.assertIn(prefix + name, text.EN)


@unittest.skipUnless(testenv.have_display(), "needs a display")
class Fits(unittest.TestCase):
    def pump(self, app, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.root.update()
            time.sleep(0.01)

    def window(self, **kw):
        from sparkclips.app import App
        app = App(opener=lambda argv: True, ask=lambda *a, **k: False, tell=lambda *a, **k: None,
                  warn=lambda *a, **k: None, error=lambda *a, **k: None, poll=False, **kw)
        self.addCleanup(app.close)
        app.root.geometry('1120x760')
        return app

    def test_no_clipped_text(self):
        app = self.window()
        self.pump(app, 0.8)
        self.assertEqual(clipped(app.root), [], "service off")
        app.apply_status({'ok': True, 'state': 'recording', 'game': 'A Very Long Game Name Indeed',
                          'source': 'steam', 'held': 12.0, 'seconds': 30, 'keep': True,
                          'only_in_game': True, 'bytes': 5_000_000, 'encoder': 'H.264 (GPU)',
                          'audio': 'AAC', 'tracks': 2, 'problem': None, 'detail': ''})
        self.pump(app, 0.5)
        self.assertEqual(clipped(app.root), [], "recording")
        app.apply_status({'ok': True, 'state': 'needs_setup', 'keep': True, 'seconds': 30,
                          'only_in_game': True, 'encoder': 'H.264 (GPU)', 'problem': None,
                          'detail': ''})
        self.pump(app, 0.5)
        self.assertEqual(clipped(app.root), [], "needs the screen")
        app.apply_status({'ok': True, 'state': 'error', 'keep': True, 'seconds': 30,
                          'only_in_game': True, 'encoder': None, 'problem': 'portal',
                          'detail': 'it broke'})
        self.pump(app, 0.5)
        self.assertEqual(clipped(app.root), [], "error")


if __name__ == '__main__':
    unittest.main()
