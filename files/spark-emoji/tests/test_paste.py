"""The pasting code against a fake XDG desktop portal (tests/fake_portal.py) on a private
session bus. Run inside `dbus-run-session` with SPARK_EMOJI_FAKE_BUS=1; skipped otherwise.
This proves Spark Emoji speaks the portal's protocol (create, select, start, then the key
presses); it can't prove that the real portal accepts it, which only a real session shows."""

import json
import os
import subprocess
import sys
import time
import unittest
import warnings

warnings.filterwarnings('ignore', message='.*get_event_loop_policy')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    from gi.repository import GLib
    HAVE_BUS = bool(os.environ.get('DBUS_SESSION_BUS_ADDRESS')) and \
        os.environ.get('SPARK_EMOJI_FAKE_BUS') == '1'
except ImportError:
    HAVE_BUS = False

if HAVE_BUS:
    from sparkemoji import paste


def spin(condition, timeout=5.0):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        if condition():
            return True
        time.sleep(0.01)
    return bool(condition())


class FakePortal:
    """Runs fake_portal.py and reads what it logged."""

    def __init__(self, *flags):
        self.log_path = os.path.join(os.environ.get('TMPDIR', '/tmp'),
                                     'spark-emoji-fake-%d-%d.log' % (os.getpid(), id(self)))
        open(self.log_path, 'w').close()
        self.proc = subprocess.Popen([sys.executable, os.path.join(HERE, 'fake_portal.py'),
                                      self.log_path, *flags])
        if not spin(lambda: any(e['method'] == 'ready' for e in self.entries()), 10):
            self.stop()
            raise RuntimeError('the fake portal did not start')

    def entries(self):
        with open(self.log_path) as f:
            return [json.loads(line) for line in f if line.strip()]

    @property
    def calls(self):
        return [e['method'] for e in self.entries()
                if e['method'] not in ('ready', 'NotifyKeyboardKeycode', 'Close')]

    @property
    def keys(self):
        return [(e['code'], e['state']) for e in self.entries()
                if e['method'] == 'NotifyKeyboardKeycode']

    def options(self, method):
        return next(e['options'] for e in self.entries() if e['method'] == method)

    def stop(self):
        self.proc.terminate()
        self.proc.wait(5)
        os.unlink(self.log_path)


@unittest.skipUnless(HAVE_BUS, 'needs a private bus: SPARK_EMOJI_FAKE_BUS=1 dbus-run-session -- ...')
class PortalTest(unittest.TestCase):

    def setUp(self):
        self.portal = None

    def tearDown(self):
        if self.portal:
            self.portal.stop()

    def open(self, *flags, token=''):
        self.portal = FakePortal(*flags)
        kb = paste.PortalKeyboard(token)
        result = []
        kb.start(lambda ok, why: result.append((ok, why)))
        spin(lambda: result)
        return kb, result

    def test_session_opens_and_remembers_token(self):
        kb, result = self.open()
        self.assertEqual(result, [(True, '')])
        self.assertEqual(kb.state, 'ready')
        self.assertEqual(kb.token, 'token-from-portal')
        self.assertEqual(self.portal.calls, ['CreateSession', 'SelectDevices', 'Start'])
        sel = self.portal.options('SelectDevices')
        self.assertEqual(sel['types'], 1)              # keyboard only
        self.assertEqual(sel['persist_mode'], 2)
        self.assertNotIn('restore_token', sel)

    def test_sends_the_token_back(self):
        self.open(token='old-token')
        self.assertEqual(self.portal.options('SelectDevices')['restore_token'], 'old-token')

    def test_paste_presses_ctrl_v(self):
        kb, _ = self.open()
        self.assertTrue(kb.paste())
        spin(lambda: len(self.portal.keys) >= 4)
        self.assertEqual(self.portal.keys, [(29, 1), (47, 1), (47, 0), (29, 0)])

    def test_paste_with_shift_for_terminals(self):
        kb, _ = self.open()
        kb.paste(shift=True)
        spin(lambda: len(self.portal.keys) >= 6)
        self.assertEqual(self.portal.keys,
                         [(29, 1), (42, 1), (47, 1), (47, 0), (42, 0), (29, 0)])

    def test_user_says_no(self):
        kb, result = self.open('--deny')
        self.assertEqual(result, [(False, 'not allowed')])
        self.assertEqual(kb.state, 'failed')
        self.assertFalse(kb.paste())
        self.assertEqual(self.portal.keys, [])

    def test_paste_before_start_does_nothing(self):
        self.assertFalse(paste.PortalKeyboard().paste())

    def test_availability(self):
        self.portal = FakePortal()
        self.assertTrue(paste.portal_available())
        self.portal.stop()
        self.portal = FakePortal('--no-keyboard')
        self.assertFalse(paste.portal_available())

    def test_no_portal_at_all(self):
        self.assertFalse(paste.portal_available())
        kb = paste.PortalKeyboard()
        result = []
        kb.start(lambda ok, why: result.append((ok, why)))
        spin(lambda: result, timeout=10)
        self.assertFalse(result[0][0])
        self.assertEqual(kb.state, 'failed')


if __name__ == '__main__':
    unittest.main()
