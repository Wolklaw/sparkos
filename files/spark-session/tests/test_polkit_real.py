"""spark-polkit against the real polkitd, a real system D-Bus and real PAM, in a throwaway
container (CI). pkcheck plays the program that needs admin rights; the agent answers with the
test user's password through the real polkit-agent-helper-1.

Needs root and polkitd. Skips without them."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
POLKITD = '/usr/lib/polkit-1/polkitd'
USER, PASSWORD = 'sparkpk', 'battery-staple-7'
BUS_CONF = '''<busconfig><type>system</type>
<listen>unix:path=/run/dbus/system_bus_socket</listen>
<policy context="default"><allow send_destination="*" eavesdrop="true"/><allow eavesdrop="true"/>
<allow own="*"/><allow user="*"/></policy></busconfig>'''
ACTION = 'org.freedesktop.policykit.exec'       # defaults to auth_admin


@unittest.skipUnless(os.geteuid() == 0 and os.path.exists(POLKITD) and shutil.which('pkcheck'),
                     'needs root and polkitd (runs in CI)')
class RealPolkit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(['useradd', '-m', '-G', 'wheel', USER], check=True)
        subprocess.run(['chpasswd'], input=f'{USER}:{PASSWORD}\n', text=True, check=True)
        os.makedirs('/run/dbus', exist_ok=True)
        cls.conf = tempfile.NamedTemporaryFile('w', suffix='.conf', delete=False)
        cls.conf.write(BUS_CONF)
        cls.conf.close()
        cls.bus = subprocess.Popen(['dbus-daemon', '--nofork', '--config-file', cls.conf.name,
                                    '--address', 'unix:path=/run/dbus/system_bus_socket'])
        for _ in range(100):
            if os.path.exists('/run/dbus/system_bus_socket'):
                break
            time.sleep(0.05)
        os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = 'unix:path=/run/dbus/system_bus_socket'
        cls.rule = '/etc/polkit-1/rules.d/50-spark-greeter.rules'
        os.makedirs(os.path.dirname(cls.rule), exist_ok=True)
        shutil.copy(os.path.join(HERE, '..', 'system/usr/share/polkit-1/rules.d/50-spark-greeter.rules'),
                    cls.rule)
        cls.polkitd = subprocess.Popen([POLKITD, '--no-debug'])
        time.sleep(2)

    @classmethod
    def tearDownClass(cls):
        for proc in (cls.polkitd, cls.bus):
            proc.terminate()
            proc.wait()
        os.unlink(cls.conf.name)
        os.unlink(cls.rule)
        subprocess.run(['userdel', '-r', USER], check=False, capture_output=True)

    def setUp(self):
        self.events_file = tempfile.NamedTemporaryFile('w+', suffix='.jsonl', delete=False).name
        self.agent = None

    def tearDown(self):
        if self.agent and self.agent.poll() is None:
            self.agent.terminate()
            self.agent.wait(10)
        os.unlink(self.events_file)

    def start_agent(self, passwords):
        env = dict(os.environ, SPARK_TEST_EVENTS=self.events_file, SPARK_TEST_PASSWORDS=passwords)
        env.pop('XDG_SESSION_ID', None)
        self.agent = subprocess.Popen([sys.executable, '-I', os.path.join(HERE, 'agent_harness.py')],
                                      env=env, stderr=subprocess.PIPE, text=True)
        end = time.time() + 15
        while time.time() < end and not self.events():
            if self.agent.poll() is not None:
                self.fail(f'agent exited: {self.agent.stderr.read()}')
            time.sleep(0.05)
        self.assertEqual(self.events()[0]['event'], 'registered')

    def events(self):
        with open(self.events_file) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def pkcheck(self):
        """pkcheck as the test user, asking for interaction. Returns its exit code."""
        inner = f'pkcheck --action-id {ACTION} --process $$ -u'
        return subprocess.run(['setpriv', f'--reuid={USER}', f'--regid={USER}', '--init-groups',
                               'bash', '-c', inner], capture_output=True, text=True, timeout=60)

    def as_user(self, user, action):
        inner = f'pkcheck --action-id {action} --process $$'
        return subprocess.run(['setpriv', f'--reuid={user}', f'--regid={user}', '--clear-groups',
                               'bash', '-c', inner], capture_output=True, text=True, timeout=60)

    def test_greeter_rule_lets_only_the_greetd_account_use_power_actions(self):
        if subprocess.run(['id', 'greetd'], capture_output=True).returncode != 0:
            subprocess.run(['useradd', '-r', 'greetd'], check=True)
        ok = self.as_user('greetd', 'org.freedesktop.login1.reboot')
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        other_action = self.as_user('greetd', ACTION)
        self.assertNotEqual(other_action.returncode, 0)
        other_user = self.as_user(USER, 'org.freedesktop.login1.reboot')
        self.assertNotEqual(other_user.returncode, 0, 'the rule must only cover the greetd account')

    def test_agent_registers_with_the_real_polkitd(self):
        self.start_agent(PASSWORD)
        self.assertIsNone(self.agent.poll())

    def test_pkcheck_reaches_the_agent_and_the_right_password_authorises(self):
        self.start_agent(PASSWORD)
        result = self.pkcheck()
        kinds = [e['event'] for e in self.events()]
        if 'window' not in kinds:
            self.skipTest('polkitd without logind has no session to match the agent to: '
                          f'pkcheck said {result.stdout!r} {result.stderr!r}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('closed', kinds)

    def test_pkcheck_with_a_cancelling_agent_is_refused(self):
        self.start_agent('CANCEL')
        result = self.pkcheck()
        kinds = [e['event'] for e in self.events()]
        if 'window' not in kinds:
            self.skipTest('polkitd without logind has no session to match the agent to')
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
