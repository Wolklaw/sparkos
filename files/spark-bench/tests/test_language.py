"""The French interface: every sentence translated with the same blanks, and text that fits.
CI runs the whole suite twice, with SPARK_LANG=en and fr."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import test_spark_bench as tsb  # noqa: E402  (sets up the temporary HOME first)
from langcheck import clipped, fields, table_problems  # noqa: E402
from sparkbench import text  # noqa: E402


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            for table in (text.EN, text.FR):
                filled = table[key].format(**{name: 'X' for name in fields(value)})
                self.assertNotIn('{', filled, key)

    def test_every_key_used_exists(self):
        import re
        folder = os.path.join(os.path.dirname(HERE), 'sparkbench')
        used = set()
        for name in os.listdir(folder):
            if name.endswith('.py'):
                with open(os.path.join(folder, name), encoding='utf-8') as f:
                    used |= set(re.findall(r"\bt\('([a-z0-9_]+\.[a-z0-9_.]+)'", f.read()))
        used = {k for k in used if not k.endswith(('_', '.'))}   # 'tab.' + name and the like
        self.assertEqual(sorted(k for k in used if k not in text.EN), [])


@unittest.skipUnless(tsb.have_display(), "needs a display")
class Fits(unittest.TestCase):
    def test_no_clipped_text(self):
        import shutil
        from sparkbench import core, library, mangohud
        tsb.fresh_home()
        folder = os.path.join(mangohud.steam_dir(), 'benchmark')
        tsb.stage(folder)
        library.Library(core.load_settings(), folder).import_files(
            [os.path.join(tsb.PM, n) for n in tsb.PM_RUNS])
        shutil.copy(os.path.join(tsb.MH, tsb.MH_RUNS[0]),
                    os.path.join(folder, 'Spider-Man2_2026-11-22_06-00-00.csv'))
        app = tsb.make_app(self, tab='setup')
        app.root.geometry('1100x720')
        app.root.update()
        self.assertEqual(clipped(app.root), [], 'setup')
        app.show('recordings')
        view = app.views['recordings']
        for iid in list(view.game_items.values())[:1] + list(view.items)[:1]:
            view.tree.selection_set(iid)
            app.root.update()
            self.assertEqual(clipped(app.root), [], 'recordings')
        app.show('compare')
        app.root.update()
        self.assertEqual(clipped(app.root), [], 'compare')


if __name__ == '__main__':
    unittest.main()
