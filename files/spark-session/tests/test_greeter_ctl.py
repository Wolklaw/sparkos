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
  cat) [ "$2" = plasmalogin.service ] && [ -z "${FAKE_NO_PLM:-}" ] ;;
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
        self.touch('usr/share/wayland-sessions/spark.desktop', '[Desktop Entry]\nName=Spark\nExec=spark\n')
        self.touch('usr/share/wayland-sessions/plasma.desktop', '[Desktop Entry]\nName=Plasma\nExec=p\n')
        os.makedirs(os.path.join(self.root, 'usr/share/spark-session'))
        shutil.copy(os.path.join(SYSTEM, 'usr/share/spark-session/greetd-config.toml'),
                    os.path.join(self.root, 'usr/share/spark-session/greetd-config.toml'))
        self.touch('etc/greetd/config.toml', '# fedora default\n[default_session]\ncommand = "agreety"\n')
        os.makedirs(os.path.join(self.root, 'etc/systemd/system'))
        os.symlink('/usr/lib/systemd/system/plasmalogin.service',
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

    def test_status_before(self):
        result = self.ctl('status')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('plasmalogin.service', result.stdout)
        self.assertIn('is off', result.stdout)
        self.assertIn('Plasma, Spark', result.stdout)
        self.assertEqual(self.calls(), [])

    def test_enable_switches_the_display_manager_without_starting_anything(self):
        result = self.ctl('enable')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.dm(), 'greetd.service')
        calls = self.calls()
        self.assertIn('disable plasmalogin.service', calls)
        self.assertIn('enable --force greetd.service', calls)
        self.assertFalse([c for c in calls if c.startswith(('start', 'stop', 'restart', 'isolate'))
                          or '--now' in c], calls)
        self.assertIn('/usr/libexec/spark-greeter-session', self.read('etc/greetd/config.toml'))
        self.assertIn('fedora default', self.read('etc/greetd/config.toml.pre-spark'))
        self.assertEqual(self.read('var/lib/spark-greeter/previous-dm').strip(), 'plasmalogin.service')

    def test_disable_is_the_exact_rollback(self):
        self.ctl('enable')
        result = self.ctl('disable')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.dm(), 'plasmalogin.service')
        self.assertIn('fedora default', self.read('etc/greetd/config.toml'))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'etc/greetd/config.toml.pre-spark')))
        self.assertFalse([c for c in self.calls() if c.startswith(('start', 'stop')) or '--now' in c])

    def test_enable_twice_keeps_the_way_back(self):
        self.ctl('enable')
        self.assertEqual(self.ctl('enable').returncode, 0)
        self.assertEqual(self.read('var/lib/spark-greeter/previous-dm').strip(), 'plasmalogin.service')
        self.ctl('disable')
        self.assertEqual(self.dm(), 'plasmalogin.service')

    def test_missing_greeter_changes_nothing(self):
        os.unlink(os.path.join(self.root, 'usr/bin/spark-greeter'))
        result = self.ctl('enable')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Nothing was changed', result.stderr)
        self.assertEqual(self.dm(), 'plasmalogin.service')
        self.assertEqual(self.calls(), [])

    def test_no_sessions_changes_nothing(self):
        for name in ('spark.desktop', 'plasma.desktop'):
            os.unlink(os.path.join(self.root, 'usr/share/wayland-sessions', name))
        self.assertNotEqual(self.ctl('enable').returncode, 0)
        self.assertEqual(self.dm(), 'plasmalogin.service')

    def test_no_plasma_login_manager_to_go_back_to_changes_nothing(self):
        env = dict(self.env, FAKE_NO_PLM='1')
        result = self.ctl('enable', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('nothing to go back to', result.stderr)
        self.assertEqual(self.dm(), 'plasmalogin.service')

    def test_auto_rollback_puts_plasma_login_manager_back_and_starts_it(self):
        self.ctl('enable')
        open(self.log, 'w').close()
        result = self.ctl('auto-rollback')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.dm(), 'plasmalogin.service')
        self.assertIn('start --no-block plasmalogin.service', self.calls())

    def test_auto_rollback_when_greetd_is_not_the_manager_does_nothing(self):
        result = self.ctl('auto-rollback')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.dm(), 'plasmalogin.service')

    def test_a_damaged_state_file_falls_back_to_plasma_login_manager(self):
        self.ctl('enable')
        self.touch('var/lib/spark-greeter/previous-dm', 'x; rm -rf /\n')
        self.ctl('disable')
        self.assertEqual(self.dm(), 'plasmalogin.service')
        self.assertNotIn('rm -rf', ' '.join(self.calls()))

    def test_real_root_needs_admin_rights(self):
        if os.geteuid() == 0:
            self.skipTest('running as root')
        env = {k: v for k, v in self.env.items() if k != 'SPARK_GREETER_ROOT'}
        result = self.ctl('enable', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('admin rights', result.stderr)


if __name__ == '__main__':
    unittest.main()
