"""The French interface, text that fits, and the window with a fake firewall and a fake sender.
Nothing here runs pkexec or touches the real firewall. The suite runs twice in CI: en and fr."""

import os
import re
import time
import unittest

import support
from langcheck import clipped, fields, table_problems
from sparkfirewall import fw, text
from sparkfirewall.lang import ui_language

PKG = os.path.join(os.path.dirname(support.HERE), 'sparkfirewall')


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            filled = text.t(key, **{name: 'X' for name in fields(value)})
            self.assertNotIn('{', filled.replace('{{', ''), key)

    def test_every_key_used_in_the_code_exists(self):
        used = set()
        for name in os.listdir(PKG):
            if name.endswith('.py') and name != 'text.py':
                with open(os.path.join(PKG, name), encoding='utf-8') as f:
                    used.update(re.findall(r"\bt\(\s*['\"]([a-z0-9_.]+)['\"]", f.read()))
        self.assertEqual(sorted(k for k in used if k not in text.EN), [])


class PickTheLanguage(unittest.TestCase):
    def test_from_the_locale(self):
        cases = [({'LANG': 'fr_CA.UTF-8'}, 'fr'), ({'LANG': 'en_CA.UTF-8'}, 'en'),
                 ({}, 'en'), ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'}, 'en'),
                 ({'LANG': 'C', 'SPARK_LANG': 'fr'}, 'fr')]
        for env, want in cases:
            with self.subTest(env=env):
                self.assertEqual(ui_language(env), want)


try:
    import tkinter as tk
    tk.Tk().destroy()
    DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
except Exception:  # noqa: BLE001 - no display, or no Tk at all
    DISPLAY = False


class Sender:
    """Stands in for pkexec: records what the window would send."""

    def __init__(self, error=None):
        self.sent = []
        self.error = error

    def __call__(self, ops):
        self.sent.append(ops)
        if self.error:
            raise self.error


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(unittest.TestCase):
    def pump(self, app, seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def make(self, runner=None, sender=None, tab=None):
        from sparkfirewall.app import App
        runner = runner or support.FakeRun()
        app = App(fw.Firewall(runner), tab=tab, sender=sender or Sender())
        self.addCleanup(app.close)
        return app

    def test_every_tab_opens_and_its_text_fits(self):
        for tab in ('overview', 'rules', 'ports'):
            app = self.make(tab=tab)
            self.pump(app, 0.8)
            app.root.geometry('%dx%d' % app.root.minsize())
            self.pump(app, 0.3)
            with self.subTest(tab=tab):
                self.assertEqual(clipped(app.root), [])

    def test_a_stopped_firewall_still_opens(self):
        for tab in ('overview', 'rules', 'ports'):
            app = self.make(support.FakeRun(running=False), tab=tab)
            self.pump(app, 0.5)
            with self.subTest(tab=tab):
                self.assertEqual(clipped(app.root), [])

    def test_a_change_waits_for_apply_and_is_sent_once(self):
        sender = Sender()
        app = self.make(sender=sender, tab='rules')
        self.pump(app, 0.5)
        app.set_service('FedoraWorkstation', 'ssh', False)
        self.assertEqual(sender.sent, [])
        self.assertEqual(len(app.pending), 1)
        app.set_service('FedoraWorkstation', 'ssh', True)   # back to how it was
        self.assertEqual(len(app.pending), 0)
        app.set_service('FedoraWorkstation', 'http', True)
        app.apply()
        self.pump(app, 0.6)
        self.assertEqual(sender.sent, [[{"op": "service", "zone": "FedoraWorkstation",
                                         "name": "http", "add": True}]])
        self.assertEqual(len(app.pending), 0)

    def test_a_cancelled_password_is_not_an_error(self):
        sender = Sender(PermissionError('cancelled'))
        app = self.make(sender=sender, tab='ports')
        self.pump(app, 0.4)
        app.set_service('FedoraWorkstation', 'http', True)
        app.apply()
        self.pump(app, 0.6)
        self.assertIsNone(app.fail)
        self.assertEqual(len(app.pending), 1)      # still there to try again

    def test_a_failure_is_shown(self):
        sender = Sender(RuntimeError('INVALID_SERVICE'))
        app = self.make(sender=sender, tab='overview')
        self.pump(app, 0.4)
        app.set_default_zone('public')
        app.apply()
        self.pump(app, 0.6)
        self.assertEqual(app.fail, 'INVALID_SERVICE')
        self.assertEqual(clipped(app.root), [])


if __name__ == '__main__':
    unittest.main()
