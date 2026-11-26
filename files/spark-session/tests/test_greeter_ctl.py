"""spark-greeter-ctl (what `spark greeter enable|disable` and the fallback unit run) against a
fake root and a fake systemctl. No real unit is touched, so it is safe anywhere."""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = os.path.join(HERE, '..', 'system')
CTL = os.path.join(SYSTEM, 'usr', 'libexec', 'spark-greeter-ctl')

FAKE_SYSTEMCTL = r'''#!/bin/bash
# Records every call; models display-manager.service as a symlink in the fake root.
echo "$*" >> "$FAKE_LOG"
root=$SPARK_GREETER_ROOT
link=$root/etc/systemd/system/display-manager.service
case "$1" in
  disable) [ -L "$link" ] && [ "$(basename "$(readlink "$link")")" = "$2" ] && rm -f "$link"; exit 0 ;;
  enable) shift; [ "$1" = --force ] && shift
          mkdir -p "$(dirname "$link")"; ln -sfn "/usr/lib/systemd/system/$1" "$link" ;;
  start) ;;
  *) exit 0 ;;
esac
'''


class CtlTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.log = os.path.join(self.root, 'calls.log')
        for rel in ('usr/bin/greetd', 'usr/bin/spark-greeter', 'usr/libexec/spark-greeter-session'):
            self.touch(rel, '#!/bin/sh\n', 0o755)
        self.touch('usr/share/wayland-sessions/spark-wl.desktop', '[Desktop Entry]\nName=Spark\nExec=spark\n')
        os.makedirs(os.path.join(self.root, 'usr/share/spark-session'))
        for name in ('greetd-config.toml', 'greetd-text.toml'):
            shutil.copy(os.path.join(SYSTEM, 'usr/share/spark-session', name),
                        os.path.join(self.root, 'usr/share/spark-session', name))
        # As the image ships it: greetd with the Spark greeter
        shutil.copy(os.path.join(SYSTEM, 'usr/share/spark-session/greetd-config.toml'),
                    self.touch('etc/greetd/config.toml', ''))
        os.makedirs(os.path.join(self.root, 'etc/systemd/system'))
        os.symlink('/usr/lib/systemd/system/greetd.service',
                   os.path.join(self.root, 'etc/systemd/system/display-manager.service'))
        self.systemctl = self.touch('fake-systemctl', FAKE_SYSTEMCTL, 0o755)
        self.env = dict(os.environ, SPARK_GREETER_ROOT=self.root, SPARK_GREETER_SYSTEMCTL=self.systemctl,
                        FAKE_LOG=self.log)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def touch(self, rel, text, mode=0o644):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write(text)
        os.chmod(path, mode)
        return path

    def ctl(self, *args, env=None):
        return subprocess.run(['bash', CTL, *args], env=env or self.env, capture_output=True, text=True)

    def dm(self):
        link = os.path.join(self.root, 'etc/systemd/system/display-manager.service')
        return os.path.basename(os.readlink(link)) if os.path.islink(link) else None

    def calls(self):
        try:
            with open(self.log) as handle:
                return handle.read().splitlines()
        except OSError:
            return []

    def read(self, rel):
        with open(os.path.join(self.root, rel)) as handle:
            return handle.read()

    def config(self):
        return self.read('etc/greetd/config.toml')

    def test_status(self):
        result = self.ctl('status')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('greetd.service', result.stdout)
        self.assertIn('Sign-in screen: Spark', result.stdout)
        self.assertIn('Sessions it will offer: Spark', result.stdout)
        self.assertEqual(self.calls(), [])

    def test_disable_switches_to_the_text_sign_in_without_starting_anything(self):
        result = self.ctl('disable')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('agreety --cmd /usr/bin/spark-wl-session', self.config())
        self.assertEqual(self.dm(), 'greetd.service')
        self.assertFalse([c for c in self.calls() if c.startswith(('start', 'stop', 'restart'))
                          or '--now' in c], self.calls())
        self.assertIn('Sign-in screen: text', self.ctl('status').stdout)

    def test_enable_puts_the_spark_greeter_back(self):
        self.ctl('disable')
        result = self.ctl('enable')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('/usr/libexec/spark-greeter-session', self.config())
        self.assertEqual(self.dm(), 'greetd.service')

    def test_enable_makes_greetd_the_display_manager_when_it_is_not(self):
        os.unlink(os.path.join(self.root, 'etc/systemd/system/display-manager.service'))
        self.assertEqual(self.ctl('enable').returncode, 0)
        self.assertEqual(self.dm(), 'greetd.service')
        self.assertIn('enable --force greetd.service', self.calls())

    def test_missing_greeter_changes_nothing(self):
        self.ctl('disable')
        os.unlink(os.path.join(self.root, 'usr/bin/spark-greeter'))
        result = self.ctl('enable')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Nothing was changed', result.stderr)
        self.assertIn('agreety', self.config())

    def test_no_sessions_changes_nothing(self):
        self.ctl('disable')
        os.unlink(os.path.join(self.root, 'usr/share/wayland-sessions/spark-wl.desktop'))
        self.assertNotEqual(self.ctl('enable').returncode, 0)
        self.assertIn('agreety', self.config())

    def test_auto_rollback_switches_to_text_and_restarts_greetd(self):
        result = self.ctl('auto-rollback')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('agreety', self.config())
        calls = self.calls()
        self.assertIn('reset-failed greetd.service', calls)
        self.assertIn('start --no-block greetd.service', calls)

    def test_auto_rollback_leaves_a_hand_made_config_alone(self):
        self.touch('etc/greetd/config.toml', '# mine\n')
        result = self.ctl('auto-rollback')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.config(), '# mine\n')
        self.assertEqual(self.calls(), [])

    def test_real_root_needs_admin_rights(self):
        if os.geteuid() == 0:
            self.skipTest('running as root')
        env = {k: v for k, v in self.env.items() if k != 'SPARK_GREETER_ROOT'}
        result = self.ctl('enable', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('admin rights', result.stderr)


if __name__ == '__main__':
    unittest.main()
