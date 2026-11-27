"""Tests for files/system/usr/libexec/spark-screen-pick: the pure logic, and the whole script run
headless (no display) with fake wlr-randr and spark-wl-windows on PATH."""
import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SCRIPT = os.path.join(ROOT, 'files/system/usr/libexec/spark-screen-pick')

loader = importlib.machinery.SourceFileLoader('spark_screen_pick', SCRIPT)
spec = importlib.util.spec_from_loader('spark_screen_pick', loader)
pick = importlib.util.module_from_spec(spec)
loader.exec_module(pick)

RANDR = [
    {'name': 'DP-1', 'enabled': True, 'make': 'Dell', 'model': 'U2723QE',
     'modes': [{'width': 1920, 'height': 1080, 'current': False},
               {'width': 3840, 'height': 2160, 'current': True}]},
    {'name': 'HDMI-A-1', 'enabled': False, 'modes': []},
    {'name': 'eDP-1', 'enabled': True, 'make': '', 'model': '', 'description': 'Built-in',
     'modes': [{'width': 1280, 'height': 800, 'current': True}]},
]
WINDOWS = [
    {'identifier': 'a1', 'title': 'Firefox', 'app_id': 'firefox'},
    {'identifier': '', 'title': 'no id', 'app_id': 'x'},
    {'identifier': 'a2', 'title': 'Share your screen', 'app_id': 'other'},
    {'identifier': 'a3', 'title': 'Picker', 'app_id': 'spark-screen-pick'},
    {'identifier': 'a1', 'title': 'dup', 'app_id': 'firefox'},
    {'identifier': 'a4', 'title': '', 'app_id': 'foot'},
]


class Logic(unittest.TestCase):
    def test_outputs(self):
        outs = pick.parse_outputs(json.dumps(RANDR))
        self.assertEqual([o['name'] for o in outs], ['DP-1', 'eDP-1'])
        self.assertEqual(outs[0]['size'], '3840x2160')
        self.assertEqual(outs[0]['desc'], 'Dell U2723QE')
        self.assertEqual(outs[1]['desc'], 'Built-in')
        self.assertEqual(outs[1]['size'], '1280x800')

    def test_outputs_garbage(self):
        for bad in ('', 'nope', '{}', 'null', '[1, "x"]'):
            self.assertEqual(pick.parse_outputs(bad), [])

    def test_windows(self):
        wins = pick.parse_windows(json.dumps(WINDOWS), own_titles=('Share your screen',))
        self.assertEqual([w['identifier'] for w in wins], ['a1', 'a4'])

    def test_windows_garbage(self):
        for bad in ('', 'x', '{}', '[null]'):
            self.assertEqual(pick.parse_windows(bad), [])

    def test_output_line(self):
        self.assertEqual(pick.output_line('Monitor', 'DP-1'), 'Monitor: DP-1')
        self.assertEqual(pick.output_line('Window', 'abc'), 'Window: abc')
        self.assertIsNone(pick.output_line('Window', ''))
        self.assertIsNone(pick.output_line('Other', 'x'))

    def test_decide(self):
        one = [{'name': 'A'}]
        two = [{'name': 'A'}, {'name': 'B'}]
        self.assertEqual(pick.decide_without_asking(two, [{'identifier': 'w'}], 'B'), ('Monitor', 'B'))
        self.assertEqual(pick.decide_without_asking(one, [], None), ('Monitor', 'A'))
        self.assertIsNone(pick.decide_without_asking(one, [{'identifier': 'w'}], None))
        self.assertIsNone(pick.decide_without_asking(two, [], None))

    def test_language(self):
        self.assertEqual(pick.ui_language({'SPARK_LANG': 'fr'}), 'fr')
        self.assertEqual(pick.ui_language({'SPARK_LANG': 'en', 'LANG': 'fr_CA.UTF-8'}), 'en')
        self.assertEqual(pick.ui_language({'LANG': 'fr_CA.UTF-8'}), 'fr')
        self.assertEqual(pick.ui_language({'LC_ALL': 'en_US.UTF-8', 'LANG': 'fr_CA'}), 'en')
        self.assertEqual(pick.ui_language({}), 'en')
        self.assertEqual(set(pick.STRINGS['en']), set(pick.STRINGS['fr']))

    def test_hint(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'screen')

            def write(text, age=0):
                with open(path, 'w') as fh:
                    fh.write(text)
                t = time.time() - age
                os.utime(path, (t, t))
            write('DP-1\n')
            self.assertEqual(pick.read_hint(['DP-1', 'eDP-1'], path), 'DP-1')
            self.assertFalse(os.path.exists(path))          # one-shot
            self.assertIsNone(pick.read_hint(['DP-1'], path))
            write('DP-1', age=pick.HINT_MAX_AGE + 5)
            self.assertIsNone(pick.read_hint(['DP-1'], path))
            write('GONE-9')
            self.assertIsNone(pick.read_hint(['DP-1'], path))
            write('  ')
            self.assertIsNone(pick.read_hint([], path))
            write('X-1')
            self.assertEqual(pick.read_hint([], path), 'X-1')


def fake(directory, name, body):
    path = os.path.join(directory, name)
    with open(path, 'w') as fh:
        fh.write('#!/bin/sh\n' + body + '\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class Headless(unittest.TestCase):
    """The script itself, with no display: the dialog cannot open, so anything that needs one
    falls back to the first screen; the paths that never ask are checked exactly."""

    def run_pick(self, randr, windows, hint=None, lang='en'):
        with tempfile.TemporaryDirectory() as d:
            bindir = os.path.join(d, 'bin')
            os.mkdir(bindir)
            fake(bindir, 'wlr-randr', f"cat <<'EOF'\n{json.dumps(randr)}\nEOF")
            if windows is None:
                fake(bindir, 'spark-wl-windows', 'exit 1')
            elif windows == 'hang':
                fake(bindir, 'spark-wl-windows', 'sleep 30')
            else:
                fake(bindir, 'spark-wl-windows',
                     f"[ \"$1\" = --ext-list ] || exit 2\ncat <<'EOF'\n{json.dumps(windows)}\nEOF")
            runtime = os.path.join(d, 'run')
            os.makedirs(os.path.join(runtime, 'spark-snip'))
            if hint:
                with open(os.path.join(runtime, 'spark-snip', 'screen'), 'w') as fh:
                    fh.write(hint)
            env = {k: v for k, v in os.environ.items() if k not in ('DISPLAY', 'WAYLAND_DISPLAY')}
            env.update(PATH=bindir + ':/usr/bin:/bin', XDG_RUNTIME_DIR=runtime, SPARK_LANG=lang)
            started = time.time()
            res = subprocess.run([sys.executable, SCRIPT], env=env, capture_output=True,
                                 text=True, timeout=30)
            return res, time.time() - started, os.path.exists(os.path.join(runtime, 'spark-snip', 'screen'))

    def test_hint_wins_and_is_consumed(self):
        res, _t, left = self.run_pick(RANDR, WINDOWS, hint='eDP-1')
        self.assertEqual((res.returncode, res.stdout), (0, 'Monitor: eDP-1\n'))
        self.assertFalse(left)

    def test_one_screen_no_windows_shares_it(self):
        res, _t, _l = self.run_pick(RANDR[:1], None)
        self.assertEqual((res.returncode, res.stdout), (0, 'Monitor: DP-1\n'))

    def test_windows_list_hanging_is_cut_off(self):
        res, took, _l = self.run_pick(RANDR[:1], 'hang')
        self.assertEqual((res.returncode, res.stdout), (0, 'Monitor: DP-1\n'))
        self.assertLess(took, 10)

    def test_nothing_to_share_cancels(self):
        res, _t, _l = self.run_pick([], None)
        self.assertEqual((res.returncode, res.stdout), (1, ''))

    def test_no_display_falls_back_to_first_screen(self):
        res, _t, _l = self.run_pick(RANDR, WINDOWS, lang='fr')
        self.assertEqual((res.returncode, res.stdout), (0, 'Monitor: DP-1\n'))


if __name__ == '__main__':
    unittest.main()
