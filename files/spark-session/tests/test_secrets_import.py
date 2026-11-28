"""Importing a GNOME Keyring file made by the real gnome-keyring-daemon."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import secrets_harness as harness  # noqa: E402
from sparksession import secrets_import as imp  # noqa: E402
from sparksession import secrets_store as store  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = {'n': 2 ** 10}


@unittest.skipUnless(harness.available(), 'gnome-keyring-daemon, dbus-run-session or secret-tool missing')
class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.home = os.path.join(cls._tmp.name, 'home')
        os.makedirs(cls.home)
        cls.path = harness.make_keyring(cls.home)
        with open(cls.path, 'rb') as handle:
            cls.data = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_parse_gives_labels_attributes_and_secrets(self):
        name, ctime, mtime, items = imp.parse_keyring(self.data, harness.PASSWORD.encode())
        self.assertEqual(name.lower(), 'login')
        got = sorted((i['label'], i['attrs'], i['secret'].decode()) for i in items)
        want = sorted((l, a, s) for l, a, s in harness.ITEMS)
        self.assertEqual(got, want)
        for it in items:
            self.assertGreater(it['created'], 1_600_000_000)
            self.assertGreaterEqual(it['modified'], it['created'])

    def test_wrong_password(self):
        with self.assertRaises(imp.WrongPassword):
            imp.parse_keyring(self.data, b'nope')

    def test_not_a_keyring(self):
        with self.assertRaises(imp.ImportError_):
            imp.parse_keyring(b'hello world, not a keyring', b'x')
        with self.assertRaises(imp.ImportError_):
            imp.parse_keyring(self.data[:60], b'hunter2')

    def test_import_twice_adds_once(self):
        _, _, _, items = imp.parse_keyring(self.data, harness.PASSWORD.encode())
        with tempfile.TemporaryDirectory() as tmp:
            v = store.Vault(os.path.join(tmp, 's'), FAST)
            v.init_master(store.wrapping_key(b'pw', 'u', FAST))
            col = v.collection('login')
            self.assertEqual(imp.import_items(v, col, items), (2, 0))
            self.assertEqual(imp.import_items(v, col, items), (0, 2))
            self.assertEqual(len(col.items), 2)
            it = col.items[v.search(col, {'service': 'example'})[0]]
            self.assertEqual((it.label, it.secret), ('First thing', b's3cret one'))

    def test_command_line_import(self):
        """The real command: password on stdin, then again (nothing added), keyfile unused."""
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, SPARK_SECRETS_DIR=os.path.join(tmp, 's'),
                       SPARK_SECRETS_KEYFILE=os.path.join(tmp, 'none'))
            env.pop('WAYLAND_DISPLAY', None)
            env.pop('DISPLAY', None)
            cmd = [sys.executable, '-s', '-m', 'sparksession.secrets_service',
                   '--import-gnome-keyring', self.path, '--password-stdin']
            first = subprocess.run(cmd, input=b'hunter2', capture_output=True, cwd=os.path.join(HERE, '..'), env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn(b'2 added, 0 already there', first.stdout)
            second = subprocess.run(cmd, input=b'hunter2', capture_output=True, cwd=os.path.join(HERE, '..'), env=env)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn(b'0 added, 2 already there', second.stdout)
            bad = subprocess.run(cmd, input=b'wrong', capture_output=True, cwd=os.path.join(HERE, '..'), env=env)
            self.assertEqual(bad.returncode, 1)
            self.assertNotIn(b'hunter2', bad.stderr)


class DeriveTests(unittest.TestCase):
    def test_derive_chains_rounds(self):
        k = imp.derive(b'pw', b'saltsalt', 3, 'sha256', 32)
        self.assertEqual(len(k), 32)
        self.assertEqual(k, imp.derive(b'pw', b'saltsalt', 3, 'sha256', 32))
        self.assertNotEqual(k, imp.derive(b'pw', b'saltsalt', 4, 'sha256', 32))
        self.assertEqual(len(imp.derive(b'pw', b'saltsalt', 1, 'sha256', 48)), 48)

    def test_reader_stops_at_the_end(self):
        with self.assertRaises(imp.ImportError_):
            imp.Reader(b'\x00\x00').u32()


if __name__ == '__main__':
    unittest.main()
