"""The window, driven the way a person would, in a temporary home with the dialogs answered by
the test. Needs a display (on CI: xvfb-run) and fontconfig; skipped without them.
Runs in both languages (SPARK_LANG)."""

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import fontkit  # noqa: E402,F401  (first: it points HOME at a temporary folder)
from fontkit import (HAVE_FC, TMP, fresh_home, pick_font, rename_family)  # noqa: E402
from langcheck import clipped  # noqa: E402

import tkinter as tk  # noqa: E402

from sparkfonts import core, fcdata, preview, store, winfonts  # noqa: E402
from sparkfonts.text import t  # noqa: E402

try:
    _probe = tk.Tk()
    _probe.destroy()
    DISPLAY = True
except tk.TclError:
    DISPLAY = False


class Answers:
    """Stands in for the dialogs: records what was shown, answers as told."""
    def __init__(self, yes=True):
        self.yes = yes
        self.asked, self.told, self.warned, self.errors = [], [], [], []

    def ask(self, title, body, **kw):
        self.asked.append((title, body))
        return self.yes

    def tell(self, title, body, **kw):
        self.told.append((title, body))

    def warn(self, title, body, **kw):
        self.warned.append((title, body))

    def error(self, title, body, **kw):
        self.errors.append((title, body))


@unittest.skipUnless(DISPLAY and HAVE_FC, "needs a display and fontconfig")
class Window(unittest.TestCase):
    def setUp(self):
        fresh_home()
        self.work = tempfile.mkdtemp(prefix='ui-', dir=TMP)
        self.say = Answers()
        self.opened = []
        self.picked = []
        self.app = None

    def tearDown(self):
        if self.app:
            try:
                self.app.close()
            except tk.TclError:
                pass

    def make(self, files=None, finder=None, yes=True):
        from sparkfonts.app import App
        self.say.yes = yes
        self.app = App(files=files, opener=lambda argv: self.opened.append(argv) or True,
                       ask=self.say.ask, tell=self.say.tell, warn=self.say.warn,
                       error=self.say.error, pick=lambda: list(self.picked),
                       windows_finder=finder)
        self.app.root.geometry('1180x760')
        self.settle()
        return self.app

    def pump(self, seconds=0.3, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not (until and until()):
            self.app.root.update()
            time.sleep(0.01)
        self.app.root.update()

    def settle(self, seconds=20):
        """Wait for the list to load and for every background job to finish."""
        self.pump(seconds, until=lambda: self.app.loaded and self.app.busy == 0)
        self.pump(0.3)
        self.assertTrue(self.app.loaded, "the list never loaded")
        self.assertEqual(self.app.busy, 0, "a background job never finished")

    def font(self, name='copy.ttf', family_stub='Zq'):
        src = pick_font()
        if not src:
            self.skipTest("no TrueType or OpenType font on this system")
        dst = os.path.join(self.work, name)
        rename_family(src, dst, family_stub + 'x' * 30)
        return dst

    def mine(self):
        return [f for f in self.app.families if f.mine]

    # ── tests ──

    def test_starts_with_the_system_fonts_and_cannot_remove_them(self):
        app = self.make()
        self.assertTrue(app.view)
        self.assertEqual(app.status_key, 'status.ready')
        self.assertTrue(app.family and app.face)
        self.assertFalse(app.b_remove.enabled)
        self.assertTrue(app.b_reveal.enabled)
        app.remove_selected()                 # does nothing and asks nothing
        self.assertEqual(self.say.asked, [])
        self.assertEqual(clipped(app.root), [], "start screen")

    def test_search_scope_and_filters(self):
        app = self.make()
        total = len(app.view)
        name = app.view[len(app.view) // 2].name
        app.search_var.set(name.lower())
        self.pump(0.5)
        self.assertTrue(0 < len(app.view) < total)
        self.assertTrue(any(f.name == name for f in app.view))
        app.search_var.set('zzzz no such font')
        self.pump(0.5)
        self.assertEqual(app.view, [])
        self.assertTrue(app.empty.winfo_ismapped())
        self.assertEqual(clipped(app.root), [], "empty list")
        app.search_var.set('')
        self.pump(0.5)
        self.assertEqual(len(app.view), total)
        app.set_scope('mine')
        self.assertEqual(app.view, [])
        app.set_scope('system')
        self.assertEqual(len(app.view), total)
        app.set_scope('all')
        app._cat_changed('mono')
        self.assertTrue(all(fcdata.category(f) == 'mono' for f in app.view))
        app._cat_changed('')

    def test_tabs_fit_in_every_state(self):
        app = self.make()
        for tab in ('preview', 'chars', 'details'):
            app.set_tab(tab)
            self.pump(1.5)
            self.assertEqual(app.tab, tab)
            self.assertEqual(clipped(app.root), [], tab)

    def test_preview_follows_the_typed_sample(self):
        if not preview.available():
            self.skipTest("Pillow isn't installed")
        app = self.make()
        app.set_tab('preview')
        self.pump(2, until=lambda: bool(app.pane_preview.blocks))
        self.assertTrue(app.pane_preview.blocks)

    def test_install_then_remove(self):
        path = self.font()
        app = self.make()
        before = len(app.families)
        self.picked = [path]
        app.install_dialog()
        self.pump(20, until=lambda: bool(self.mine()))
        self.settle()
        self.assertEqual(len(app.families), before + 1)
        fam = self.mine()[0]
        self.assertEqual(app.family.name, fam.name)          # the new font is selected
        self.assertEqual(app.status_key, 'status.installed')
        self.assertTrue(all(fcdata.is_user_font(f.path) for f in fam.faces))
        self.assertTrue(app.b_remove.enabled)
        self.assertEqual(self.say.warned, [])
        self.assertEqual(clipped(app.root), [], "after install")
        app.set_scope('mine')
        self.assertEqual([f.name for f in app.view], [fam.name])
        paths = [f.path for f in fam.faces]
        app.remove_selected()
        self.assertEqual(len(self.say.asked), 1)
        self.assertIn(fam.name, self.say.asked[0][1])
        self.pump(20, until=lambda: not self.mine())
        self.settle()
        self.assertFalse(any(os.path.exists(p) for p in paths))
        self.assertEqual(self.mine(), [])
        self.assertEqual(app.status_key, 'status.removed')
        self.assertEqual(os.listdir(core.fonts_dir()), [])

    def test_remove_declined_keeps_the_font(self):
        path = self.font()
        app = self.make()
        self.picked = [path]
        app.install_dialog()
        self.pump(20, until=lambda: bool(self.mine()))
        self.settle()
        self.say.yes = False
        app.remove_selected()
        self.pump(0.5)
        self.assertEqual(len(self.mine()), 1)
        self.assertTrue(all(os.path.exists(f.path) for f in self.mine()[0].faces))

    def test_install_refuses_a_file_that_is_not_a_font(self):
        junk = os.path.join(self.work, 'junk.ttf')
        with open(junk, 'wb') as f:
            f.write(b'hello, not a font')
        app = self.make()
        app.install_paths([junk])
        self.pump(10, until=lambda: bool(self.say.warned))
        self.settle()
        self.assertEqual(len(self.say.warned), 1)
        self.assertIn('junk.ttf', self.say.warned[0][1])
        self.assertEqual(self.mine(), [])
        self.assertEqual(os.listdir(core.fonts_dir()), [])

    def test_installing_a_system_font_says_it_is_already_here(self):
        app = self.make()
        app.install_paths([pick_font()])
        self.pump(10, until=lambda: bool(self.say.warned))
        self.settle()
        self.assertEqual(len(self.say.warned), 1)
        self.assertEqual(self.mine(), [])

    def test_a_different_copy_asks_before_replacing(self):
        path = self.font()
        app = self.make()
        app.install_paths([path])
        self.pump(20, until=lambda: bool(self.mine()))
        self.settle()
        other = os.path.join(self.work, 'other.ttf')
        with open(path, 'rb') as f:
            data = f.read()
        with open(other, 'wb') as f:
            f.write(data + b'\0' * 8)
        self.say.yes = False
        app.install_paths([other])
        self.pump(10, until=lambda: bool(self.say.asked))
        self.settle()
        self.assertEqual(len(self.say.asked), 1)
        self.assertEqual(len(os.listdir(os.path.join(core.fonts_dir(), self.mine()[0].name))), 1)
        self.say.yes = True
        app.install_paths([other])
        self.pump(20, until=lambda: len(self.say.asked) == 2)
        self.settle()
        names = os.listdir(os.path.join(core.fonts_dir(), self.mine()[0].name))
        self.assertEqual(names, ['other.ttf'])

    def test_open_files_previews_without_installing(self):
        path = self.font()
        app = self.make(files=[path])
        self.pump(15, until=lambda: app.scope == 'opened')
        self.settle()
        self.assertEqual(app.scope, 'opened')
        self.assertEqual(len(app.pending_families), 1)
        self.assertEqual(os.listdir(core.fonts_dir()), [])
        self.assertTrue(app.b_add.winfo_ismapped())
        self.assertFalse(app.b_remove.enabled)
        self.assertEqual(clipped(app.root), [], "opened")
        app.install_opened()
        self.pump(20, until=lambda: bool(self.mine()))
        self.settle()
        self.assertEqual(len(self.mine()), 1)
        self.assertEqual(app.pending_families, [])
        self.assertEqual(app.scope, 'all')

    def test_broken_files_are_listed_and_removable(self):
        folder = os.path.join(core.fonts_dir(), 'Junk')
        os.makedirs(folder)
        bad = os.path.join(folder, 'broken.ttf')
        with open(bad, 'wb') as f:
            f.write(b'not a font')
        app = self.make()
        self.assertEqual(app.broken, [bad])
        app.set_scope('broken')
        self.pump(0.3)
        self.assertEqual(list(app.rows.values()), [bad])
        self.assertEqual(app.broken_path, bad)
        self.assertEqual(clipped(app.root), [], "broken")
        app.remove_selected()
        self.pump(15, until=lambda: not os.path.exists(bad))
        self.settle()
        self.assertFalse(os.path.exists(bad))
        self.assertEqual(app.broken, [])
        self.assertEqual(app.scope, 'all')

    def test_reveal_runs_the_opener(self):
        app = self.make()
        app.reveal_selected()
        self.assertTrue(self.opened)

    def test_windows_fonts_dialog(self):
        font = pick_font()
        if not font:
            self.skipTest("no TrueType or OpenType font on this system")
        root = os.path.join(self.work, 'winc')
        fonts = os.path.join(root, 'Windows', 'Fonts')
        os.makedirs(fonts)
        rename_family(font, os.path.join(fonts, 'WINFONT.TTF'), 'Zw' + 'x' * 30)
        with open(os.path.join(fonts, 'desktop.ini'), 'w') as f:
            f.write('x')
        # the system font on the "drive" is already installed here, so it isn't offered
        shutil.copy(font, os.path.join(fonts, 'SYSTEM.TTF'))
        app = self.make(finder=lambda: (winfonts.windows_sources(root), ''))
        app.windows_dialog()
        dialog = app.windows
        self.pump(20, until=lambda: bool(dialog.tree.get_children()))
        self.assertEqual(len(dialog.tree.get_children()), 1)
        self.assertEqual(clipped(dialog), [], "windows dialog")
        self.assertEqual(len(dialog.chosen), 1)
        dialog.do_import()
        self.pump(20, until=lambda: bool(self.mine()))
        self.settle()
        self.assertEqual(len(self.mine()), 1)
        self.assertTrue(dialog.closed)

    def test_windows_dialog_problem_is_said_in_words(self):
        app = self.make(finder=lambda: ([], 'no_drive'))
        app.windows_dialog()
        dialog = app.windows
        self.pump(5, until=lambda: dialog.status.cget('text') == t('win.problem.no_drive'))
        self.assertEqual(dialog.status.cget('text'), t('win.problem.no_drive'))
        self.assertEqual(clipped(dialog), [], "windows problem")
        dialog.close()

    def test_dropped_files_install(self):
        path = self.font()
        app = self.make()
        app._xdnd_drop([path], 'copy', 10, 10)
        self.pump(20, until=lambda: bool(self.mine()))
        self.settle()
        self.assertEqual(len(self.mine()), 1)

    def test_listing_many_families_stays_quick(self):
        app = self.make()
        faces = []
        for i in range(900):
            faces.append(fcdata.Face(path=f'/usr/share/fonts/x/F{i}.ttf', family=f'Many {i}',
                                     style='Regular', langs=frozenset({'en'})))
        families = fcdata.group(faces)
        app.families = families
        start = time.monotonic()
        for _ in range(5):
            app.refilter()
            app.root.update()
        self.assertLess((time.monotonic() - start) / 5, 1.0)
        start = time.monotonic()
        for _ in range(30):
            app.tree.yview_scroll(5, 'units')
            app.root.update()
        self.assertLess(time.monotonic() - start, 3.0)


if __name__ == '__main__':
    unittest.main()
