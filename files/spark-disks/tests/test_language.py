"""The French interface, text that fits, and the window with a fake backend (nothing real is
touched). The whole suite runs twice in CI, with SPARK_LANG=en and fr."""

import os
import re
import time
import unittest

import support
from langcheck import clipped, fields, table_problems
from sparkdisks import safety, text
from sparkdisks.lang import ui_language
from support import FakeBackend, find, tree

PKG = os.path.join(os.path.dirname(support.HERE), 'sparkdisks')
# keys the code builds from a prefix, listed here so a rename can't leave one behind
PREFIXES = ('refuse', 'note', 'bad', 'err', 'tag', 'smart', 'problem', 'verdict', 'tab', 'what',
            'done', 'status', 'btn', 'field', 'dlg', 'dialog', 'hint', 'detail', 'fact', 'col',
            'drives', 'health', 'image', 'fs')


def sources():
    for name in sorted(os.listdir(PKG)):
        if name.endswith('.py') and name not in ('text.py', 'lang.py'):
            with open(os.path.join(PKG, name), encoding='utf-8') as f:
                yield name, f.read()


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            for table in (text.EN, text.FR):
                filled = table[key].format(**{name: 'X' for name in fields(value)})
                self.assertNotIn('{', filled, key)
            filled = text.t(key, **{name: 'X' for name in fields(value)})
            self.assertTrue(filled, key)

    def test_every_key_used_in_the_code_exists(self):
        used = set()
        pattern = re.compile(r"""['"]((?:%s)\.[a-z0-9_]+)['"]""" % '|'.join(PREFIXES))
        for _name, body in sources():
            used.update(pattern.findall(body))
        # smart.py names problems 'smart.x'; the window shows them as 'problem.x'
        missing = sorted(k for k in used if k not in text.EN
                         and not (k.startswith('smart.') and 'problem.' + k[6:] in text.EN)
                         and k != 'smart.not_read')
        self.assertEqual(missing, [])
    def test_every_refusal_the_rules_can_give_has_a_sentence(self):
        with open(os.path.join(PKG, 'safety.py'), encoding='utf-8') as f:
            keys = set(re.findall(r"['\"](refuse\.[a-z_]+)['\"]", f.read()))
        with open(os.path.join(PKG, 'ops.py'), encoding='utf-8') as f:
            keys |= set(re.findall(r"['\"](refuse\.[a-z_]+)['\"]", f.read()))
        self.assertTrue(keys)
        self.assertEqual(sorted(k for k in keys if k not in text.EN), [])

    def test_every_check_note_exists(self):
        self.assertIn('note.unmounted_first', text.EN)


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
        os.environ['SPARK_DISKS_REDUCED_MOTION'] = '1'
        self.addCleanup(os.environ.pop, 'SPARK_DISKS_REDUCED_MOTION', None)
        self.backend = FakeBackend()
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            try:
                app.close()
            except Exception:  # noqa: BLE001
                pass

    def open(self, tab='drives'):
        from sparkdisks.app import App
        app = App(tab=tab, backend=self.backend, lister=tree)
        self.apps.append(app)
        self.pump(app, 0.5)
        return app

    def pump(self, app, seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def test_every_tab_opens_and_its_text_fits(self):
        for tab in ('drives', 'health', 'image'):
            app = self.open(tab)
            app.root.geometry('%dx%d' % app.root.minsize())
            self.pump(app, 0.3)
            with self.subTest(tab=tab):
                self.assertEqual(clipped(app.root), [])
            app.close()
            self.apps.remove(app)
        self.assertFalse(self.backend.changed_anything())

    def pick(self, app, path):
        view = app.view('drives')
        view.tree.selection_set(path)
        self.pump(app, 0.1)
        return view

    def test_d_has_every_button_off(self):
        app = self.open()
        for path in ('/dev/sparksa', '/dev/sparksa1'):
            view = self.pick(app, path)
            for action, button in view.buttons.items():
                self.assertFalse(button.enabled, (path, action))
            self.assertIn(text.t('refuse.d').split('.')[0][:10], view.reason.cget('text'))

    def test_the_system_mounts_cannot_be_unmounted_or_formatted(self):
        app = self.open()
        view = self.pick(app, '/dev/sparkn0p3')
        for action in ('unmount', 'format', 'delete', 'resize'):
            self.assertFalse(view.buttons[action].enabled, action)

    def test_a_stick_can_be_formatted_and_a_disabled_button_does_nothing(self):
        app = self.open()
        view = self.pick(app, '/dev/sparksb2')
        self.assertTrue(view.buttons['format'].enabled)
        view = self.pick(app, '/dev/sparksa1')
        view.act('format')
        self.pump(app, 0.3)
        self.assertEqual(self.backend.calls, [])

    def test_hard_dialog_needs_the_name_and_cancel_changes_nothing(self):
        from sparkdisks.dialogs import Ask, _Window
        app = self.open()
        spec = Ask('Format', 'Format', [], [], [], typed='sparksc1')
        win = _Window(app, spec)
        self.pump(app, 0.1)
        self.assertFalse(win.go.enabled)
        win.typed_var.set('sparksc')
        self.assertFalse(win.go.enabled)
        win.typed_var.set('sparksc1')
        self.assertTrue(win.go.enabled)
        win.typed_var.set('SPARKSC1')
        self.assertFalse(win.go.enabled)
        win._go()                                   # disabled: nothing happens
        self.assertIsNone(spec.result)
        win.close()
        self.assertIsNone(spec.result)
        self.assertFalse(self.backend.changed_anything())

    def test_dialog_returns_the_typed_name(self):
        from sparkdisks.dialogs import Ask, _Window
        app = self.open()
        spec = Ask('Format', 'Format', [], [], [], typed='sparksc1')
        win = _Window(app, spec)
        win.typed_var.set('sparksc1')
        win._go()
        self.assertEqual(spec.result, {'confirm': 'sparksc1'})

    def test_a_stale_row_is_not_acted_on(self):
        """Pick the stick, let it vanish, press a button: the gate refuses."""
        app = self.open()
        self.pick(app, '/dev/sparksb1')
        gone = [d for d in tree() if d.path != '/dev/sparksb']
        app.lister = lambda: gone
        app.ops.lister = app.lister
        app.view('drives').act('unmount')
        self.pump(app, 0.5)
        self.assertEqual([c for c in self.backend.calls if c[0] == 'unmount'], [])

    def test_a_drive_the_list_cannot_read_says_so(self):
        from sparkdisks.app import App

        def broken():
            raise OSError('no lsblk')
        app = App(tab='drives', backend=self.backend, lister=broken)
        self.apps.append(app)
        self.pump(app, 0.6)
        self.assertIn('no lsblk', app.view('drives').empty.cget('text'))


if __name__ == '__main__':
    unittest.main()
