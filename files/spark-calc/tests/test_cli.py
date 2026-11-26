"""The command line, the app description and the per-user install (Linux, not as root)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)

from sparkcalc import APP_ID, VERSION  # noqa: E402
from sparkcalc.text import t  # noqa: E402

LINUX = sys.platform.startswith('linux')
ROOT = hasattr(os, 'geteuid') and os.geteuid() == 0


def cli(*args, env=None):
    return subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_calc.py'), *args],
                          capture_output=True, text=True, encoding='utf-8', timeout=60,
                          env=env)


class CommandLine(unittest.TestCase):
    def test_version(self):
        r = cli('--version')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), f"Spark Calc {VERSION}")

    def test_self_test(self):
        r = cli('--self-test')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('sums:      16 of 16 right', r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith('self-test passed'))

    def test_eval(self):
        self.assertEqual(cli('--eval', '0.1+0.2').stdout.strip(), '0.3')
        self.assertEqual(cli('--eval', 'sin(pi/2)', '--angle', 'rad').stdout.strip(), '1')
        self.assertEqual(cli('--eval', '0x7F+1', '--mode', 'programmer', '--bits', '8',
                             '--base', 'hex').stdout.strip(), '80')
        r = cli('--eval', '1/0')
        self.assertEqual(r.returncode, 1)
        self.assertIn(t('err.div_zero'), r.stderr)

    def test_no_tk_needed_without_a_window(self):
        code = ("import sys; sys.modules['tkinter'] = None; sys.path.insert(0, %r); "
                "from sparkcalc.cli import main; sys.exit(main(['--eval', '2+2']))" % APP_DIR)
        r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                           timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, '4'), r.stderr)


class Description(unittest.TestCase):
    def test_spark_app_json(self):
        with open(os.path.join(APP_DIR, 'spark-app.json'), encoding='utf-8') as f:
            meta = json.load(f)
        self.assertEqual(meta['id'], APP_ID)
        self.assertEqual(meta['version'], VERSION)
        self.assertFalse(meta['needs']['root'])
        self.assertTrue(os.path.isfile(os.path.join(APP_DIR, meta['icon'])))

    def test_desktop_entry(self):
        with open(os.path.join(APP_DIR, f'{APP_ID}.desktop'), encoding='utf-8') as f:
            text = f.read()
        self.assertIn('\nExec=spark-calc\n', text)
        self.assertIn(f'\nIcon={APP_ID}\n', text)
        self.assertIn('\nStartupWMClass=SparkCalc\n', text)

    def test_icons(self):
        for size in (16, 22, 24, 32, 48, 64, 128, 256, 512):
            self.assertTrue(os.path.isfile(os.path.join(APP_DIR, 'icons',
                                                         f'spark-calc-{size}.png')), size)
        self.assertTrue(os.path.isfile(os.path.join(APP_DIR, 'icons', 'spark-calc.svg')))


@unittest.skipUnless(LINUX and not ROOT and shutil.which('bash'), "Linux, as a normal user")
class UserInstall(unittest.TestCase):
    def test_install_and_uninstall_leave_nothing(self):
        home = tempfile.mkdtemp(prefix='spark-calc-home-')
        env = {'HOME': home, 'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
               'LANG': 'C.UTF-8'}
        script = os.path.join(APP_DIR, 'install.sh')
        r = subprocess.run(['bash', script, '--user'], capture_output=True, text=True,
                           env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('self-test passed', r.stdout)
        bin_path = os.path.join(home, '.local', 'bin', 'spark-calc')
        self.assertTrue(os.access(bin_path, os.X_OK))
        with open(os.path.join(home, '.local', 'share', 'applications', f'{APP_ID}.desktop'),
                  encoding='utf-8') as f:
            entry = f.read()
        self.assertIn(f'\nExec={bin_path}\n', entry)
        self.assertIn(f'\nExec={bin_path} --mode programmer\n', entry)
        out = subprocess.run([bin_path, '--eval', '6*7'], capture_output=True, text=True,
                             env=env, timeout=60)
        self.assertEqual(out.stdout.strip(), '42')
        r = subprocess.run(['bash', script, '--user', '--uninstall'], capture_output=True,
                           text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        left = [os.path.join(d, n) for d, dirs, files in os.walk(home) for n in dirs + files
                if 'spark' in n.lower() and 'calc' in n.lower()]
        self.assertEqual(left, [])
        shutil.rmtree(home, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
